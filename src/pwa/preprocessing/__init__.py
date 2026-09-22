"""Data preprocessing and ETL pipeline subpackage — Nexora Enterprise Platform.

Contains modules for:
  - Multi-dataset Kaggle download (kaggle_download.py)
  - BigQuery infrastructure setup (bigquery_setup.py)
  - Metadata/control plane setup (pwa_metadata_setup.py)
  - Raw ingestion per source (adventureworks_ingest.py, olist_ingest.py, olist_marketing_ingest.py)
  - Staging normalization (staging_enterprise.py, staging_marketplace.py)
  - Curated model building (curated_enterprise.py, curated_marketplace.py)
  - BigQuery mart view creation (bigquery_mart.py)
  - Generic utilities (bigquery_load_csv.py, bigquery_replicate.py)
"""

from pwa.preprocessing.bigquery_setup import run_setup
from pwa.preprocessing.kaggle_download import download_all_datasets

__all__ = [
    "download_all_datasets",
    "run_setup",
]
