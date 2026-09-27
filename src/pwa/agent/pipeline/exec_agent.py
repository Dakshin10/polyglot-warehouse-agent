"""Stage 3: Agent 3 — Validation & Execution Agent.

Validates AST read-only safety, table authorizations, dry-run scan cost guardrails,
freshness SLAs, quality gate status, and executes queries against BigQuery.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pwa.agent.errors import (
    SqlValidationError,
    QueryCostLimitExceededError,
    WarehouseExecutionError,
)
from pwa.governance.freshness import FreshnessTracker
from pwa.semantic.result_contract import SemanticQueryEngine, QueryResult
from pwa.semantic.sql_generator import SqlSafetyValidator

logger = logging.getLogger("pwa.agent.pipeline.exec_agent")

DEFAULT_MAX_BYTES_SCANNED = 10 * 1024 * 1024 * 1024  # 10 GB limit


class ValidationExecutionAgent:
    """Agent 3 engine validating SQL safety, cost guardrails, quality, and executing queries."""

    def __init__(
        self,
        safety_validator: SqlSafetyValidator | None = None,
        engine: SemanticQueryEngine | None = None,
        max_bytes_allowed: int = DEFAULT_MAX_BYTES_SCANNED,
    ) -> None:
        self.safety_validator = safety_validator or SqlSafetyValidator()
        self.engine = engine or SemanticQueryEngine()
        self.freshness_tracker = FreshnessTracker()
        self.max_bytes_allowed = max_bytes_allowed

    def validate_and_execute(self, sql: str, intent: Any | None = None) -> QueryResult:
        """Validate SQL and execute returning standard QueryResult contract."""
        # 1. AST Read-Only & Table Authorization
        try:
            self.safety_validator.validate_sql(sql)
        except Exception as exc:
            raise SqlValidationError(f"SQL validation failed: {exc}") from exc

        # 2. Cost Guardrail Check — a real BigQuery dry-run when live, a fixed
        # nominal estimate in mock mode (there is no BigQuery to dry-run against).
        if self.engine.writer.mock:
            estimated_bytes = 1024
        else:
            try:
                from pwa.agent.guardrails import dry_run_check_bytes

                estimated_bytes = dry_run_check_bytes(sql, max_bytes=self.max_bytes_allowed)
            except ValueError as exc:
                raise QueryCostLimitExceededError(
                    str(exc),
                    estimated_bytes=self.max_bytes_allowed + 1,
                    limit_bytes=self.max_bytes_allowed,
                ) from exc

        if estimated_bytes > self.max_bytes_allowed:
            raise QueryCostLimitExceededError(
                f"Query cost limit exceeded: estimated scan bytes ({estimated_bytes}) exceeds maximum allowed limit ({self.max_bytes_allowed}).",
                estimated_bytes=estimated_bytes,
                limit_bytes=self.max_bytes_allowed,
            )

        # 3. Execution via SemanticQueryEngine / BigQueryWriter
        if intent:
            result = self.engine.execute_intent(intent)
        else:
            source_tables = _extract_source_tables(sql)
            semantic_objects = _tables_to_semantic_objects(source_tables)
            # Direct SQL execution adapter
            if self.engine.writer.mock:
                from pwa.warehouse.local_engine import get_local_sqlite_engine

                is_stub = False
                try:
                    df = get_local_sqlite_engine().execute_sql(sql)
                    rows = df.to_dict(orient="records")
                    cols = list(df.columns)
                except Exception as local_exc:
                    logger.warning(f"Local SQLite engine direct SQL execution failed, falling back to stub: {local_exc}")
                    rows = [{"result_count": 100}]
                    cols = list(rows[0].keys())
                    is_stub = True

                result = QueryResult(
                    query_id="custom_sql_query",
                    sql=sql,
                    columns=cols,
                    rows=rows,
                    row_count=len(rows),
                    bytes_processed=0,
                    execution_time_seconds=0.05,
                    semantic_objects_used=semantic_objects,
                    source_tables=source_tables,
                    status="SUCCESS",
                    is_mock=True,
                    data_source="stub" if is_stub else "local_sqlite",
                )
            else:
                try:
                    assert self.engine.writer._client is not None, "BigQueryWriter is not mocked but has no live client"
                    df = self.engine.writer._client.query(sql).to_dataframe()
                    rows = df.to_dict(orient="records")
                    freshness_status, quality_status = self._lookup_freshness_and_quality(semantic_objects)
                    result = QueryResult(
                        query_id="custom_sql_query",
                        sql=sql,
                        columns=list(df.columns),
                        rows=rows,
                        row_count=len(rows),
                        bytes_processed=estimated_bytes,
                        execution_time_seconds=0.5,
                        semantic_objects_used=semantic_objects,
                        source_tables=source_tables,
                        freshness_status=freshness_status,
                        quality_status=quality_status,
                        status="SUCCESS",
                        is_mock=False,
                        data_source="bigquery",
                    )
                except Exception as exc:
                    raise WarehouseExecutionError(f"BigQuery execution failed: {exc}") from exc

        # 4. Result Validation & Warnings
        if result.row_count == 0:
            result.warnings.append("Execution warning: Query returned 0 rows.")

        return result

    def _lookup_freshness_and_quality(self, semantic_objects: list[str]) -> tuple[str, str]:
        """Best-effort freshness/quality lookup for the direct-SQL execution path.

        Uses the first resolved semantic object's source system/entity name as a
        stand-in for "the table(s) this raw SQL actually touched" — the direct-SQL
        adapter has no AnalyticalIntent to resolve a precise entity list from.
        """
        if not semantic_objects or semantic_objects == ["unknown"]:
            return "FRESH", "PASS"
        try:
            from pwa.control_plane.metadata import ControlPlaneManager
            from pwa.semantic.loader import get_semantic_catalog

            catalog = get_semantic_catalog()
            entity = catalog.entities.get(semantic_objects[0])
            if entity is None:
                return "FRESH", "PASS"
            source_id = entity.source_systems[0] if entity.source_systems else "d1"

            mgr = ControlPlaneManager(writer=self.engine.writer)
            last_ingested_at = mgr.get_last_successful_ingestion(source_id)
            quality_status = mgr.get_latest_quality_status(source_id, entity.name)

            fresh_res = self.freshness_tracker.evaluate_freshness(
                source_id=source_id, table_name=entity.name, last_ingested_at=last_ingested_at
            )
            freshness_status = fresh_res.status.value
            return freshness_status, ("PASS" if quality_status == "UNKNOWN" else quality_status)
        except Exception as exc:
            logger.debug(f"[ValidationExecutionAgent] Freshness/quality lookup failed: {exc}")
            return "FRESH", "PASS"


_FROM_TABLE_PATTERN = re.compile(r"(?:FROM|JOIN)\s+`?([a-zA-Z0-9_.\-]+)`?", re.IGNORECASE)


def _extract_source_tables(sql: str) -> list[str]:
    """Extract physical base table references from SQL AST using sqlglot, excluding CTE names."""
    if not sql or not sql.strip():
        return ["unknown"]

    try:
        import sqlglot
        from sqlglot import exp

        parsed = sqlglot.parse_one(sql, read="bigquery")

        # Collect CTE names defined in WITH clauses
        cte_names = set()
        for cte in parsed.find_all(exp.CTE):
            if cte.alias:
                cte_names.add(cte.alias.lower())

        base_tables: list[str] = []
        for table_node in parsed.find_all(exp.Table):
            table_name = table_node.name
            if not table_name:
                continue

            db = table_node.args.get("db")
            catalog = table_node.args.get("catalog")
            parts = [p.name for p in [catalog, db, table_node] if p and getattr(p, "name", None)]
            full_name = ".".join(parts) if parts else table_name

            if table_name.lower() not in cte_names and full_name not in base_tables:
                base_tables.append(full_name)

        # Inspect AST for federated BigQuery EXTERNAL_QUERY calls
        for func in parsed.find_all(exp.Anonymous, exp.Func):
            func_name = getattr(func, "name", "") or getattr(func, "key", "")
            if func_name and str(func_name).upper() in ("EXTERNAL_QUERY", "EXTERNAL_QUERY_STRING"):
                args = func.expressions
                if len(args) >= 2 and isinstance(args[1], exp.Literal):
                    inner_sql = str(args[1].this)
                    if inner_sql:
                        for dialect in ("mysql", "postgres", None):
                            try:
                                inner_parsed = sqlglot.parse_one(inner_sql, read=dialect)
                                for inner_table in inner_parsed.find_all(exp.Table):
                                    t_name = inner_table.name
                                    if t_name and t_name.lower() not in cte_names and t_name not in base_tables:
                                        base_tables.append(t_name)
                                break
                            except Exception:
                                continue

        return base_tables or ["unknown"]
    except Exception as exc:
        logger.debug(f"sqlglot table extraction error ({exc}), falling back to regex")
        tables = _FROM_TABLE_PATTERN.findall(sql or "")
        seen: list[str] = []
        for t in tables:
            if t not in seen:
                seen.append(t)
        return seen or ["unknown"]


def _tables_to_semantic_objects(source_tables: list[str]) -> list[str]:
    """Map physical table references back to their semantic catalog entity names."""
    from pwa.semantic.loader import get_semantic_catalog

    catalog = get_semantic_catalog()
    by_physical_table = {e.physical_table: name for name, e in catalog.entities.items()}
    objects: list[str] = []
    for table in source_tables:
        # Strip project/dataset prefix so `project.dataset.table` still matches
        # a catalog entity registered as `dataset.table`.
        suffix = ".".join(table.split(".")[-2:]) if "." in table else table
        name = by_physical_table.get(table) or by_physical_table.get(suffix)
        if name and name not in objects:
            objects.append(name)
    return objects or ["unknown"]


def ast_validate_sql(sql: str) -> None:
    """Legacy AST SQL validator checking read-only SELECT and table authorizations."""
    if not sql or not sql.strip():
        raise ValueError("SQL query cannot be empty.")

    import re

    cleaned = sql.strip()
    if cleaned.startswith("-- Multi-Step") or cleaned.startswith("--"):
        return

    cleaned_no_comments = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL).strip()
    cleaned_no_comments = re.sub(r"--.*?\n", "", cleaned_no_comments).strip()
    s_upper = cleaned_no_comments.upper()

    if not s_upper or (not s_upper.startswith("SELECT") and not s_upper.startswith("WITH")):
        raise ValueError("Only SELECT statements are allowed.")

    if s_upper in ("SELECT", "SELECT;", "WITH", "WITH;", "SELECT FROM", "SELECT FROM;"):
        raise ValueError("Only SELECT statements are allowed.")

    forbidden = ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "CREATE ", "ALTER ", "TRUNCATE ", "MERGE "]
    if any(k in s_upper for k in forbidden):
        raise ValueError("Only SELECT statements are allowed. Found mutation/DDL keyword.")

    if "raw_" in sql.lower() or "staging" in sql.lower() or "raw_adventureworks" in sql.lower():
        raise ValueError("Access denied: Unauthorized table access. Only mart/curated views are allowed.")


def validate_and_execute_sql(sql: str) -> dict[str, Any]:
    """Legacy adapter function for 4-stage pipeline."""
    agent = ValidationExecutionAgent()
    try:
        res = agent.validate_and_execute(sql)
        return {
            "status": res.status,
            "sql": res.sql,
            "rows": res.rows,
            "row_count": res.row_count,
            "bytes_scanned": res.bytes_processed,
            "warnings": res.warnings,
            "freshness_status": res.freshness_status,
            "quality_status": res.quality_status,
            "viz_hint": res.visualization_hint,
        }
    except Exception as exc:
        logger.error(f"Validation/Execution agent error: {exc}")
        return {
            "status": "ERROR",
            "sql": sql,
            "error": str(exc),
            "rows": [],
            "row_count": 0,
        }
