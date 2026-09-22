"""BigQuery mart view builder — Nexora Enterprise Platform.

Builds curated mart views from raw and staging layers.
Replaces the old movie-specific mart_views.sql and mart_descriptions.sql.

Enterprise mart views target:
  - curated_enterprise.*   (sales, products, employees, procurement)
  - curated_marketplace.*  (orders, customers, sellers, marketing funnel)

The _split_sql_statements() and _execute_sql_file() utilities are preserved
as generic infrastructure.
"""

import logging

from google.cloud import bigquery

from pwa.connections import get_bq_client
from pwa.settings import get_settings
from pwa.sql_files import sql_file_path

logger = logging.getLogger("pwa.bigquery_mart")


def _split_sql_statements(sql_text: str) -> list[str]:
    """Split SQL file into statements by semicolon, respecting single-quoted strings."""
    statements = []
    current: list[str] = []
    in_quote = False
    i = 0
    while i < len(sql_text):
        char = sql_text[i]
        if char == "'":
            if in_quote and i + 1 < len(sql_text) and sql_text[i + 1] == "'":
                current.append("''")
                i += 2
                continue
            in_quote = not in_quote
            current.append(char)
        elif char == ";" and not in_quote:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(char)
        i += 1
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements


def _execute_sql_file(
    client: bigquery.Client,
    filename: str,
    project: str,
    label: str,
    subdirectory: str = "",
) -> bool:
    """Read a SQL file, substitute {PROJECT}, and execute each statement."""
    from pathlib import Path

    # Support subdirectory (e.g., sql/enterprise/)
    if subdirectory:
        # Locate from project root
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        sql_path = repo_root / "sql" / subdirectory / filename
    else:
        sql_path = Path(sql_file_path(filename))

    try:
        with open(sql_path, "r", encoding="utf-8") as fh:
            raw_sql = fh.read()
    except OSError as e:
        logger.error(f"{label}: SQL file '{sql_path}' not found ({e}).")
        return False

    sql = raw_sql.replace("{PROJECT}", project)
    statements = _split_sql_statements(sql)

    logger.info(f"{label}: Executing {len(statements)} statements from {sql_path}...")

    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=500_000_000)
    failed = 0
    for idx, stmt in enumerate(statements, 1):
        if not stmt or (stmt.startswith("--") and "\n" not in stmt):
            continue
        try:
            client.query(stmt, job_config=job_config).result()
            first_line = stmt.split("\n")[0][:60]
            logger.info(f"  [{idx}/{len(statements)}] OK: {first_line}...")
        except Exception as e:
            failed += 1
            logger.error(f"  [{idx}/{len(statements)}] FAILED: {e}")
            logger.error(f"  Statement: {stmt[:200]}...")

    if failed > 0:
        logger.error(f"{label}: {failed} statement(s) failed.")
        return False
    logger.info(f"{label}: All {len(statements)} statements executed successfully.")
    return True


def build_mart() -> bool:
    """Build all enterprise curated mart views and descriptions."""
    s = get_settings()
    project = s.gcp_project
    client = get_bq_client()

    logger.info("=== BUILDING NEXORA ENTERPRISE MART LAYER ===")

    results = []

    # Enterprise views (curated_enterprise)
    for sql_file in ["views_enterprise.sql", "views_marketplace.sql", "views_integrity.sql"]:
        ok = _execute_sql_file(client, sql_file, project, sql_file.upper(), subdirectory="enterprise")
        results.append((sql_file, ok))

    failed = [f for f, ok in results if not ok]
    if failed:
        logger.error(f"Mart build had errors in: {failed}. Check logs above.")
        return False

    logger.info("Re-authorizing curated views on source datasets...")
    from pwa.preprocessing.bigquery_setup import authorize_curated_views

    authorize_curated_views(client, project)

    logger.info("=== ENTERPRISE MART LAYER BUILD COMPLETE ===")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if build_mart() else 1)
