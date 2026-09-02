import os
import sys
import logging
from dotenv import load_dotenv
from google.cloud import bigquery
from pwa.warehouse.setup import authorize_mart_views

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_mart")


def _split_sql_statements(sql_text):
    """Split SQL file into statements by semicolon, respecting single-quoted strings."""
    statements = []
    current = []
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


def _execute_sql_file(client, sql_path, project, label):
    """Read a SQL file, replace {PROJECT}, and execute each statement."""
    filename = os.path.basename(sql_path)
    raw_sql = None
    try:
        from importlib.resources import files

        raw_sql = files("pwa.sql.mart").joinpath(filename).read_text(encoding="utf-8")
    except Exception:
        if not os.path.exists(sql_path):
            sql_path = os.path.join(".", "src", "pwa", "sql", "mart", filename)
        if os.path.exists(sql_path):
            with open(sql_path, "r", encoding="utf-8") as f:
                raw_sql = f.read()

    if raw_sql is None:
        logger.error(f"{label}: SQL file '{filename}' not found.")
        sys.exit(1)

    sql = raw_sql.replace("{PROJECT}", project)
    statements = _split_sql_statements(sql)

    logger.info(f"{label}: Executing {len(statements)} statements from {sql_path}...")

    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=100_000_000)
    failed = 0
    for idx, stmt in enumerate(statements, 1):
        if not stmt or stmt.startswith("--") and "\n" not in stmt:
            continue
        try:
            client.query(stmt, job_config=job_config).result()
            first_line = stmt.split("\n")[0][:60]
            logger.info(f"  [{idx}/{len(statements)}] OK: {first_line}...")
        except Exception as e:
            failed += 1
            logger.error(f"  [{idx}/{len(statements)}] FAILED: {e}")
            logger.error(f"  Statement: {stmt[:120]}...")

    if failed > 0:
        logger.error(f"{label}: {failed} statement(s) failed.")
        return False
    else:
        logger.info(f"{label}: All {len(statements)} statements executed successfully.")
        return True


def build_mart():
    """Build all mart views and apply all column descriptions."""
    load_dotenv()
    project = os.getenv("GCP_PROJECT", "").strip()
    location = os.getenv("BQ_LOCATION", "EU").strip()

    if not project:
        logger.error("GCP_PROJECT not set in .env. Cannot proceed.")
        sys.exit(1)

    client = bigquery.Client(project=project, location=location)

    logger.info("=== STEP 3: BUILD MART LAYER ===")

    mart_sql_path = os.path.join(".", "src", "pwa", "sql", "mart", "views.sql")
    if not os.path.exists(mart_sql_path):
        mart_sql_path = os.path.join(".", "sql", "bq_mart.sql")
    mart_ok = _execute_sql_file(client, mart_sql_path, project, "MART VIEWS")

    desc_sql_path = os.path.join(".", "src", "pwa", "sql", "mart", "descriptions.sql")
    if not os.path.exists(desc_sql_path):
        desc_sql_path = os.path.join(".", "sql", "bq_descriptions.sql")
    desc_ok = _execute_sql_file(client, desc_sql_path, project, "MART DESCRIPTIONS")

    if not mart_ok or not desc_ok:
        logger.error("Mart layer build had errors. See logs above.")
        sys.exit(1)

    logger.info("Re-authorizing mart views on raw datasets after recreation...")
    authorize_mart_views(client, project)

    logger.info("=== MART LAYER BUILD COMPLETE ===")
    return True


if __name__ == "__main__":
    build_mart()
