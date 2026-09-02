import os
import sys
import logging

import pandas as pd
from google.cloud import bigquery

from pwa.connections import get_bq_client
from pwa.settings import get_settings

logger = logging.getLogger("pwa.bigquery_load_csv")

OUT_DIR = os.path.join(".", "data", "out")

BQ_SCHEMA_KEYWORDS = [
    bigquery.SchemaField("movie_id", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("keyword_id", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("keyword", "STRING"),
]

BQ_SCHEMA_RATINGS = [
    bigquery.SchemaField("movie_id", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("movielens_id", "INT64"),
    bigquery.SchemaField("imdb_id", "INT64"),
    bigquery.SchemaField("rating_count", "INT64"),
    bigquery.SchemaField("avg_rating", "NUMERIC"),
    bigquery.SchemaField("min_rating", "NUMERIC"),
    bigquery.SchemaField("max_rating", "NUMERIC"),
]


def _load_csv_to_bq(client, csv_path, table_id, schema, table_label):
    """Load a CSV file into a BigQuery table with explicit schema and WRITE_TRUNCATE."""
    if not os.path.exists(csv_path):
        logger.error(f"{table_label} CSV not found at {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path)
    logger.info(f"Read {len(df)} rows from {csv_path}")

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    logger.info(f"Loading CSV into BigQuery `{table_id}` (WRITE_TRUNCATE)...")
    with open(csv_path, "rb") as source_file:
        job = client.load_table_from_file(source_file, table_id, job_config=job_config)
    job.result()

    table = client.get_table(table_id)
    logger.info(f"BigQuery reported row count for `{table_id}`: {table.num_rows}")
    return table.num_rows


def load_csvs():
    """Load both CSVs into BigQuery raw_files dataset."""
    settings = get_settings()
    project = settings.gcp_project
    ds_files = settings.bq_ds_files

    client = get_bq_client()

    keywords_path = os.path.join(OUT_DIR, "movie_keywords.csv")
    keywords_table = f"{project}.{ds_files}.movie_keywords"
    kw_rows = _load_csv_to_bq(client, keywords_path, keywords_table, BQ_SCHEMA_KEYWORDS, "movie_keywords")

    ratings_path = os.path.join(OUT_DIR, "movie_ratings_agg.csv")
    ratings_table = f"{project}.{ds_files}.movie_ratings_agg"
    rat_rows = _load_csv_to_bq(client, ratings_path, ratings_table, BQ_SCHEMA_RATINGS, "movie_ratings_agg")

    logger.info(f"=== CSV LOADING COMPLETE: movie_keywords={kw_rows}, movie_ratings_agg={rat_rows} ===")
    return kw_rows, rat_rows


if __name__ == "__main__":
    load_csvs()
