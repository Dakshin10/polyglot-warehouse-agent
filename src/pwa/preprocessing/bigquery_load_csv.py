"""Generic BigQuery CSV loader — Nexora Enterprise Platform.

PRESERVED AS GENERIC INFRASTRUCTURE:
This module provides generic CSV → BigQuery loading utilities.
The movie-specific schemas (BQ_SCHEMA_KEYWORDS, BQ_SCHEMA_RATINGS)
and the movie file hardcoding have been removed.

For the primary enterprise pipeline, use the ingest modules:
  adventureworks_ingest.py  (Kaggle Excel → raw_adventureworks.*)
  olist_ingest.py           (Kaggle CSV → raw_olist.*)
  olist_marketing_ingest.py (Kaggle CSV → raw_olist_marketing.*)

This module can be used for ad-hoc CSV loads in future integrations.
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from google.cloud import bigquery

from pwa.connections import get_bq_client

logger = logging.getLogger("pwa.bigquery_load_csv")


def load_csv_to_bq(
    csv_path: str | Path,
    table_id: str,
    schema: Optional[list] = None,
    write_disposition: str = "WRITE_TRUNCATE",
    table_label: str = "csv",
) -> int:
    """Load a CSV file into a BigQuery table.

    Args:
        csv_path:          Path to the CSV file.
        table_id:          Fully qualified BigQuery table reference (project.dataset.table).
        schema:            Explicit schema field list. If None, autodetect.
        write_disposition: "WRITE_TRUNCATE" (default), "WRITE_APPEND", or "WRITE_EMPTY".
        table_label:       Label for log messages.

    Returns:
        Number of rows loaded.
    """
    csv_path = Path(csv_path)
    client = get_bq_client()

    if not csv_path.exists():
        logger.error(f"[{table_label}] CSV file not found: {csv_path}")
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    logger.info(f"[{table_label}] Reading CSV: {csv_path}")
    df = pd.read_csv(csv_path, low_memory=False)
    logger.info(f"[{table_label}] Read {len(df):,} rows from {csv_path.name}")

    disposition_map = {
        "WRITE_TRUNCATE": bigquery.WriteDisposition.WRITE_TRUNCATE,
        "WRITE_APPEND": bigquery.WriteDisposition.WRITE_APPEND,
        "WRITE_EMPTY": bigquery.WriteDisposition.WRITE_EMPTY,
    }

    job_config = bigquery.LoadJobConfig(
        write_disposition=disposition_map.get(write_disposition, bigquery.WriteDisposition.WRITE_TRUNCATE),
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    if schema:
        job_config.schema = schema
    else:
        job_config.autodetect = True

    records = df.to_dict(orient="records")

    logger.info(f"[{table_label}] Loading {len(records):,} rows → `{table_id}` ({write_disposition})...")
    job = client.load_table_from_json(records, table_id, job_config=job_config)
    job.result()

    final_count = client.get_table(table_id).num_rows
    logger.info(f"[{table_label}] BigQuery `{table_id}` row count: {final_count:,}")
    return final_count


def load_csvs() -> None:
    """Deprecated stub — movie-specific CSV loading is not used in the enterprise pipeline.

    The enterprise pipeline does not load from data/out/ (movie outputs).
    Use adventureworks_ingest, olist_ingest, olist_marketing_ingest for enterprise ingestion.
    """
    logger.warning("load_csvs() is not part of the enterprise pipeline. Use the enterprise ingest modules instead.")


if __name__ == "__main__":
    from pwa.logging_setup import setup_logging

    setup_logging()
    logger.info("bigquery_load_csv.py: generic CSV→BigQuery utility. Use load_csv_to_bq() for ad-hoc loads.")
