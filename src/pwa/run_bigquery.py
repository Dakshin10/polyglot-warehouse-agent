import logging
from pwa.bigquery_setup import run_setup
from pwa.bigquery_mart import build_mart
from pwa.bigquery_replicate import replicate_mysql
from pwa.bigquery_load_csv import load_csvs
from pwa.gates_bigquery import run_all_bq_gates as run_warehouse_gates

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bq_pipeline")


def run_warehouse_pipeline():
    """Run full BigQuery pipeline end-to-end: Setup -> Land Data -> Build Mart -> Verify."""
    logger.info("=========================================================")
    logger.info("   STARTING BIGQUERY LANDING + MART PIPELINE             ")
    logger.info("=========================================================")

    logger.info("\n---> STEP 1: BIGQUERY SETUP (datasets, connection, IAM)")
    run_setup()

    logger.info("\n---> STEP 2.2: REPLICATE AIVEN MYSQL -> raw_registry.movie")
    replicate_mysql()

    logger.info("\n---> STEP 2.3: LOAD CSVs -> raw_files")
    load_csvs()

    logger.info("\n---> STEP 3: BUILD MART LAYER")
    build_mart()

    logger.info("\n---> STEP 5: BIGQUERY VERIFICATION GATES")
    run_warehouse_gates()

    logger.info("\n=========================================================")
    logger.info("   BIGQUERY PIPELINE COMPLETED SUCCESSFULLY (EXIT 0)     ")
    logger.info("=========================================================")


if __name__ == "__main__":
    run_warehouse_pipeline()
