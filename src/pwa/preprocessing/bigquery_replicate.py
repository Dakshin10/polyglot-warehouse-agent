"""Generic MySQL → BigQuery table replication utility — Nexora Enterprise Platform.

PRESERVED AS GENERIC INFRASTRUCTURE:
This module provides generic MySQL table replication. The movie-specific schema
(BQ_SCHEMA_MOVIE) and movie table hardcoding have been removed.

For the primary enterprise pipeline, use the ingest modules instead:
  adventureworks_ingest.py  (Kaggle Excel → raw_adventureworks.*)
  olist_ingest.py           (Kaggle CSV → raw_olist.*)
  olist_marketing_ingest.py (Kaggle CSV → raw_olist_marketing.*)

This module can be used for live MySQL sources in future integrations.
"""

import logging
from typing import Optional

import pandas as pd
from google.cloud import bigquery

from pwa.connections import get_bq_client, get_mysql_engine
from pwa.settings import get_settings

logger = logging.getLogger("pwa.bigquery_replicate")


def replicate_mysql_table(
    source_table: str,
    target_dataset: str,
    target_table: Optional[str] = None,
    schema: Optional[list] = None,
    sql: Optional[str] = None,
) -> int:
    """Replicate a MySQL table (or query result) to a BigQuery table.

    Args:
        source_table:   MySQL table name (used as default SQL if sql not provided).
        target_dataset: BigQuery dataset ID.
        target_table:   BigQuery table name (defaults to source_table).
        schema:         Explicit BigQuery schema field list. If None, autodetect.
        sql:            Custom SQL to execute on MySQL (defaults to SELECT * FROM source_table).

    Returns:
        Number of rows written to BigQuery.
    """
    s = get_settings()
    project = s.gcp_project

    if not s.mysql_enabled:
        raise RuntimeError(
            "MySQL is not configured (MYSQL_HOST and MYSQL_PASSWORD are required). "
            "Set them in .env to use MySQL replication."
        )

    mysql_engine, mysql_type = get_mysql_engine()
    query = sql or f"SELECT * FROM {source_table}"

    logger.info(f"Reading from MySQL ({mysql_type}): {query}")
    df = pd.read_sql(query, con=mysql_engine)
    logger.info(f"Read {len(df):,} rows from MySQL table '{source_table}'")

    if df.empty:
        logger.error(f"MySQL table '{source_table}' returned 0 rows.")
        return 0

    bq_table_name = target_table or source_table
    table_id = f"{project}.{target_dataset}.{bq_table_name}"
    client = get_bq_client()

    records = df.to_dict(orient="records")
    # Convert date-like values to ISO string for JSON serialization
    for r in records:
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                r[k] = v.isoformat() if v is not None else None

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    if schema:
        job_config.schema = schema
    else:
        job_config.autodetect = True

    logger.info(f"Loading {len(records):,} rows → `{table_id}` (WRITE_TRUNCATE)...")
    job = client.load_table_from_json(records, table_id, job_config=job_config)
    job.result()

    final_count = client.get_table(table_id).num_rows
    logger.info(f"BigQuery `{table_id}` row count: {final_count:,}")
    return final_count


def replicate_mysql() -> int:
    """Deprecated stub — MySQL replication is not used in the primary enterprise pipeline.

    Preserved for backward compatibility. The enterprise pipeline uses direct
    Kaggle-to-BigQuery ingestion (adventureworks_ingest, olist_ingest, olist_marketing_ingest).

    Returns 0. Does not raise.
    """
    logger.warning(
        "replicate_mysql() called but is not part of the primary enterprise pipeline. "
        "Use adventureworks_ingest, olist_ingest, or olist_marketing_ingest instead."
    )
    return 0


if __name__ == "__main__":
    from pwa.logging_setup import setup_logging

    setup_logging()
    logger.info(
        "bigquery_replicate.py: generic MySQL→BigQuery utility. "
        "Use adventureworks_ingest / olist_ingest / olist_marketing_ingest for enterprise ingestion."
    )
