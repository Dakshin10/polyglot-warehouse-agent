import logging
from pwa.kaggle_download import download_dataset
from pwa.movie_transform import transform_and_select
from pwa.source_db_load import load_data
from pwa.gates_source import run_all_gates as run_source_gates

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pipeline")


def run_source_pipeline():
    """Run full source ETL pipeline end-to-end: Download -> Transform -> Load -> Verify."""
    logger.info("=========================================================")
    logger.info("   STARTING END-TO-END DATA ENGINEERING PIPELINE         ")
    logger.info("=========================================================")

    logger.info("\n---> STEP 1: DOWNLOAD KAGGLE DATASET")
    download_dataset()

    logger.info("\n---> STEP 2: TRANSFORM & SELECT TOP 1000 CANDIDATES")
    mysql_df, pg_df = transform_and_select()

    logger.info("\n---> STEP 3: LOAD INTO AIVEN MYSQL & CLOUD SQL POSTGRESQL")
    load_data(mysql_df=mysql_df, pg_df=pg_df)

    logger.info("\n---> STEP 4: RUN VERIFICATION GATES 1-13")
    run_source_gates()

    logger.info("\n=========================================================")
    logger.info("   PIPELINE COMPLETED SUCCESSFULLY (EXIT 0)             ")
    logger.info("=========================================================")


if __name__ == "__main__":
    run_source_pipeline()
