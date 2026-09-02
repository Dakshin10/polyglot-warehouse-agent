import os
import logging
from dotenv import load_dotenv
from google.cloud import bigquery

logger = logging.getLogger("db")


def get_bq_client(project: str = "", location: str = "") -> bigquery.Client:
    """Create BigQuery client for project and location."""
    load_dotenv()
    proj = project or os.getenv("GCP_PROJECT", "").strip()
    loc = location or os.getenv("BQ_LOCATION", "EU").strip()
    return bigquery.Client(project=proj, location=loc)
