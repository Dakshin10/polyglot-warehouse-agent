"""Warehouse pipeline: setup -> land -> mart -> gates B1-B15."""

import logging

from pwa.bigquery_load_csv import load_csvs
from pwa.bigquery_mart import build_mart
from pwa.bigquery_replicate import replicate_mysql
from pwa.bigquery_setup import run_setup
from pwa.gates_bigquery import run_all_bq_gates

logger = logging.getLogger("pwa.run_bigquery")


def run_warehouse_pipeline() -> bool:
    """Run the BigQuery landing and mart build end to end. Returns True only if gates B1-B15 all passed."""
    logger.info("=========================================================")
    logger.info("   STARTING BIGQUERY LANDING + MART PIPELINE             ")
    logger.info("=========================================================")

    logger.info("---> STEP 1: BIGQUERY SETUP (datasets, connection, IAM)")
    run_setup()

    logger.info("---> STEP 2: REPLICATE AIVEN MYSQL -> raw_registry.movie")
    replicate_mysql()

    logger.info("---> STEP 3: LOAD CSVs -> raw_files")
    load_csvs()

    logger.info("---> STEP 4: BUILD MART LAYER")
    build_mart()

    logger.info("---> STEP 5: BIGQUERY VERIFICATION GATES B1-B15")
    passed = run_all_bq_gates()

    logger.info("=========================================================")
    if passed:
        logger.info("   BIGQUERY PIPELINE COMPLETED SUCCESSFULLY (EXIT 0)     ")
    else:
        logger.error("   BIGQUERY PIPELINE FAILED: GATES DID NOT PASS (EXIT 1) ")
    logger.info("=========================================================")
    return passed


if __name__ == "__main__":
    raise SystemExit(0 if run_warehouse_pipeline() else 1)
