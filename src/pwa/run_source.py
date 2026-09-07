"""Source pipeline: download -> transform -> load -> gates 1-13."""

import logging

from pwa.gates_source import run_all_gates
from pwa.preprocessing import download_dataset, load_data, transform_and_select


logger = logging.getLogger("pwa.run_source")


def run_source_pipeline() -> bool:
    """Run the source ETL end to end. Returns True only if gates 1-13 all passed."""
    logger.info("=========================================================")
    logger.info("   STARTING END-TO-END DATA ENGINEERING PIPELINE         ")
    logger.info("=========================================================")

    logger.info("---> STEP 1: DOWNLOAD KAGGLE DATASET")
    download_dataset()

    logger.info("---> STEP 2: TRANSFORM & SELECT TOP 1000 CANDIDATES")
    mysql_df, pg_df = transform_and_select()

    logger.info("---> STEP 3: LOAD INTO AIVEN MYSQL & CLOUD SQL POSTGRESQL")
    load_data(mysql_df=mysql_df, pg_df=pg_df)

    logger.info("---> STEP 4: RUN VERIFICATION GATES 1-13")
    passed = run_all_gates()

    logger.info("=========================================================")
    if passed:
        logger.info("   SOURCE PIPELINE COMPLETED SUCCESSFULLY (EXIT 0)      ")
    else:
        logger.error("   SOURCE PIPELINE FAILED: GATES DID NOT PASS (EXIT 1)  ")
    logger.info("=========================================================")
    return passed


if __name__ == "__main__":
    raise SystemExit(0 if run_source_pipeline() else 1)
