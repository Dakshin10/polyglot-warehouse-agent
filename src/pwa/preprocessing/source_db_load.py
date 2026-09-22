"""Source database load utility — Nexora Enterprise Platform.

PRESERVED FOR OPTIONAL FUTURE USE:
MySQL and PostgreSQL are no longer required by the primary ingestion pipeline,
which loads data directly from Kaggle files to BigQuery native tables.

If a live-source connector to MySQL or PostgreSQL is needed in the future,
this module provides the generic load infrastructure. The table names,
DDL scripts, and schema definitions should be replaced with enterprise-domain
equivalents at that time.

The primary ingestion flow is now:
  kaggle_download.py
    → adventureworks_ingest.py  (→ raw_adventureworks.*)
    → olist_ingest.py           (→ raw_olist.*)
    → olist_marketing_ingest.py (→ raw_olist_marketing.*)
"""

import logging

logger = logging.getLogger("pwa.source_db_load")


def load_data(*args, **kwargs) -> None:
    """Stub: MySQL/PostgreSQL loading is not used in the primary enterprise pipeline.

    The primary ingestion goes directly from Kaggle files to BigQuery raw tables.
    See: adventureworks_ingest.py, olist_ingest.py, olist_marketing_ingest.py

    Raises:
        NotImplementedError: Always. This module is preserved for future optional use.
    """
    logger.warning(
        "load_data() called on source_db_load.py stub. "
        "The primary enterprise pipeline does not use MySQL/PostgreSQL. "
        "Use the ingest modules instead: "
        "adventureworks_ingest, olist_ingest, olist_marketing_ingest."
    )
    raise NotImplementedError(
        "source_db_load.load_data() is not used in the enterprise pipeline. "
        "Direct BigQuery ingestion is the primary path."
    )
