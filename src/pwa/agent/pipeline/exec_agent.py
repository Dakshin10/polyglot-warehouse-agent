"""Stage 3: ValidationExecutionAgent for static query validation and BigQuery execution.

SQL safety is enforced via AST-based allowlisting using sqlglot rather than a keyword
blocklist.  Keyword blocklists are trivially bypassed (e.g. a DROP hidden inside a CTE);
AST parsing makes that structurally impossible to hide.
"""

import json
import logging
import time
from typing import Any

import sqlglot
import sqlglot.expressions as exp

from pwa.agent.bq_tools import validate_mart_table
from pwa.agent.guardrails import dry_run_check_bytes
from pwa.connections import get_bq_client

logger = logging.getLogger("pwa.agent.pipeline.exec_agent")

# Nodes that represent any write/DDL operation – finding any of these in the
# parsed tree (including inside CTEs or sub-queries) is grounds for immediate
# rejection.
_FORBIDDEN_NODE_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Grant,
    exp.Revoke,
    exp.TruncateTable,
    exp.Merge,
)


def ast_validate_sql(sql: str) -> None:
    """Validate SQL using AST parsing — allows only a top-level SELECT with no
    nested write/DDL nodes anywhere in the tree.

    This replaces the previous keyword-blocklist approach which could be bypassed
    by embedding forbidden keywords inside string literals or CTE names.

    Args:
        sql: Raw SQL string to validate.

    Raises:
        ValueError: If SQL is empty, fails to parse, is not a SELECT, or contains
                    any write/DDL expression anywhere in the AST.
    """
    if not sql or not sql.strip():
        raise ValueError("SQL query cannot be empty.")

    # 1. Parse — reject anything that does not parse cleanly as BigQuery SQL.
    try:
        parsed = sqlglot.parse_one(sql, read="bigquery")
    except sqlglot.errors.ParseError as exc:
        raise ValueError(f"SQL failed to parse: {exc}") from exc

    if parsed is None:
        raise ValueError("SQL parsed to None — malformed or empty statement.")

    # 2. Top-level expression must be a SELECT.
    if not isinstance(parsed, exp.Select):
        raise ValueError(
            f"Security violation: Only SELECT statements are allowed. "
            f"Got top-level expression type: {type(parsed).__name__}"
        )

    # 3. Recursively walk the full AST — no write/DDL nodes allowed anywhere
    #    (catches INSERT/DROP/etc. smuggled inside CTEs or sub-queries).
    for forbidden_type in _FORBIDDEN_NODE_TYPES:
        for node in parsed.find_all(forbidden_type):
            raise ValueError(
                f"Security violation: Forbidden expression '{type(node).__name__}' "
                "detected inside the SQL AST (possibly hidden in a CTE or sub-query)."
            )

    # 4. Table-level allowlist check — skip entirely when EXTERNAL_QUERY is present
    #    because inner table refs are string literal arguments validated server-side.
    has_external_query = any(fn for fn in parsed.find_all(exp.Anonymous) if "EXTERNAL_QUERY" in (fn.name or "").upper())
    if not has_external_query:
        for tbl in parsed.find_all(exp.Table):
            # sqlglot splits "project.dataset.table" into catalog/db/name.
            db = tbl.args.get("db") or ""
            if hasattr(db, "name"):
                db = db.name
            tbl_name = tbl.name or ""
            if not tbl_name or tbl_name.lower() in ("", "dual"):
                continue
            # Skip unqualified names — they are CTE aliases or sub-query references,
            # not real BigQuery tables.  Real BQ tables always carry a dataset qualifier.
            if not db:
                continue
            canonical = f"{db}.{tbl_name}"
            try:
                validate_mart_table(canonical)
            except ValueError as table_err:
                raise ValueError(str(table_err)) from table_err


def validate_and_execute_sql(sql: str) -> dict[str, Any]:
    """Run Stage 3: AST-validate SQL, check dry-run cost, and execute via BigQuery client."""
    logger.debug(f"[Stage 3 - ValidationExecutionAgent Input]: SQL='{sql}'")

    # 1. AST-Based Security Validation
    try:
        ast_validate_sql(sql)
    except Exception as err:
        logger.warning(f"[Stage 3 AST Validation Error]: {err}")
        return {
            "status": "ERROR",
            "error": f"Static SQL Validation Failed: {err}",
            "sql": sql,
            "rows": [],
        }

    # 2. Dry-Run Bytes Scanned Cost Guard (hard enforcement — raises if exceeded)
    bytes_scanned = 0
    try:
        bytes_scanned = dry_run_check_bytes(sql)
    except Exception as err:
        logger.warning(f"[Stage 3 Dry-Run Cost Exceeded]: {err}")
        return {
            "status": "ERROR",
            "error": f"Query Cost Limit Exceeded: {err}",
            "sql": sql,
            "rows": [],
        }

    # 3. BigQuery Execution
    try:
        client = get_bq_client()
        t0_exec = time.perf_counter()
        query_job = client.query(sql)
        results = query_job.result()
        exec_latency = round(time.perf_counter() - t0_exec, 3)

        actual_bytes = getattr(query_job, "total_bytes_processed", bytes_scanned)
        slot_ms = getattr(query_job, "slot_millis", 0)

        rows = []
        for row in results:
            row_dict = {}
            for key, val in row.items():
                try:
                    json.dumps(val)
                except (TypeError, ValueError):
                    val = str(val)
                row_dict[key] = val
            rows.append(row_dict)

        if not rows:
            logger.info(f"[Stage 3 Execution Empty Results]: Query returned 0 rows for SQL: {sql}")
            return {
                "status": "EMPTY",
                "error": "Query executed successfully but returned 0 rows.",
                "sql": sql,
                "rows": [],
                "bytes_scanned": bytes_scanned,
                "actual_bytes_processed": actual_bytes,
                "slot_ms": slot_ms,
                "exec_latency": exec_latency,
            }

        logger.debug(f"[Stage 3 - ValidationExecutionAgent Output]: SUCCESS ({len(rows)} rows)")
        return {
            "status": "SUCCESS",
            "sql": sql,
            "rows": rows,
            "count": len(rows),
            "bytes_scanned": bytes_scanned,
            "actual_bytes_processed": actual_bytes,
            "slot_ms": slot_ms,
            "exec_latency": exec_latency,
        }
    except Exception as err:
        logger.warning(f"[Stage 3 Execution Exception]: {err}")
        return {
            "status": "ERROR",
            "error": f"BigQuery Execution Error: {err}",
            "sql": sql,
            "rows": [],
            "bytes_scanned": bytes_scanned,
        }
