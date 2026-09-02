import os
import sys
import logging
from dotenv import load_dotenv
import pandas as pd
from google.cloud import bigquery
from pwa.db import get_mysql_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("replicate_mysql")

BQ_SCHEMA_MOVIE = [
    bigquery.SchemaField("movie_id", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("title", "STRING"),
    bigquery.SchemaField("original_title", "STRING"),
    bigquery.SchemaField("original_language", "STRING"),
    bigquery.SchemaField("release_date", "DATE"),
    bigquery.SchemaField("release_year", "INT64"),
    bigquery.SchemaField("runtime_min", "INT64"),
    bigquery.SchemaField("budget_usd", "INT64"),
    bigquery.SchemaField("revenue_usd", "INT64"),
    bigquery.SchemaField("primary_genre", "STRING"),
    bigquery.SchemaField("production_country", "STRING"),
    bigquery.SchemaField("vote_average", "NUMERIC"),
    bigquery.SchemaField("vote_count", "INT64"),
    bigquery.SchemaField("popularity", "NUMERIC"),
]


def replicate_mysql():
    """Read movie table from Aiven MySQL and load into BigQuery raw_registry.movie."""
    load_dotenv()
    project = os.getenv("GCP_PROJECT", "").strip()
    ds_registry = os.getenv("BQ_DS_REGISTRY", "raw_registry").strip()
    location = os.getenv("BQ_LOCATION", "EU").strip()

    if not project:
        logger.error("GCP_PROJECT not set in .env. Cannot proceed.")
        sys.exit(1)

    logger.info("Reading movie table from Aiven MySQL via get_mysql_engine()...")
    mysql_engine, mysql_type = get_mysql_engine()
    df = pd.read_sql("SELECT * FROM movie", con=mysql_engine)
    logger.info(f"Read {len(df)} rows from MySQL ({mysql_type})")

    if len(df) == 0:
        logger.error("MySQL movie table returned 0 rows. Cannot replicate.")
        sys.exit(1)

    records = df.to_dict(orient="records")
    for r in records:
        if r.get("release_date") is not None and pd.notna(r["release_date"]):
            r["release_date"] = str(r["release_date"])
        else:
            r["release_date"] = None

    table_id = f"{project}.{ds_registry}.movie"
    client = bigquery.Client(project=project, location=location)

    job_config = bigquery.LoadJobConfig(
        schema=BQ_SCHEMA_MOVIE,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    logger.info(f"Loading {len(records)} rows into BigQuery `{table_id}` (WRITE_TRUNCATE)...")
    job = client.load_table_from_json(records, table_id, job_config=job_config)
    job.result()

    table = client.get_table(table_id)
    logger.info(f"BigQuery reported row count for `{table_id}`: {table.num_rows}")

    if table.num_rows != 1000:
        logger.warning(f"Expected 1000 rows but BigQuery reports {table.num_rows}")

    logger.info("=== MYSQL REPLICATION TO BIGQUERY COMPLETE ===")
    return table.num_rows


if __name__ == "__main__":
    replicate_mysql()
