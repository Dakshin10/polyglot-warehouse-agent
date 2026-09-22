"""Warehouse pipeline — Nexora Enterprise Platform.

Flow:
  BigQuery setup → metadata setup → staging → curated → mart views → gates B1-B15
"""

import logging

logger = logging.getLogger("pwa.run_bigquery")


def run_warehouse_pipeline() -> bool:
    """Run the BigQuery warehouse pipeline end to end.

    Returns True only if all pipeline stages succeeded and gates B1-B15 passed.
    """
    from pwa.preprocessing.bigquery_setup import run_setup
    from pwa.preprocessing.pwa_metadata_setup import run_metadata_setup
    from pwa.preprocessing.bigquery_mart import build_mart
    from pwa.gates_bigquery import run_all_bq_gates

    logger.info("=" * 65)
    logger.info("   NEXORA BIGQUERY WAREHOUSE PIPELINE STARTING              ")
    logger.info("=" * 65)

    passed = True

    logger.info("---> STEP 1: BIGQUERY INFRASTRUCTURE SETUP (datasets, IAM)")
    try:
        run_setup()
    except Exception as exc:
        logger.error(f"BigQuery setup failed: {exc}")
        passed = False

    if passed:
        logger.info("---> STEP 2: METADATA CONTROL PLANE SETUP")
        try:
            run_metadata_setup()
        except Exception as exc:
            logger.error(f"Metadata setup failed: {exc}")
            passed = False

    if passed:
        logger.info("---> STEP 3: BUILD MART VIEWS (curated enterprise + marketplace)")
        try:
            build_mart()
        except Exception as exc:
            logger.error(f"Mart build failed: {exc}")
            passed = False

    if passed:
        logger.info("---> STEP 4: BIGQUERY VERIFICATION GATES B1-B15")
        try:
            passed = run_all_bq_gates()
        except Exception as exc:
            logger.error(f"BigQuery gates raised exception: {exc}")
            passed = False

    logger.info("=" * 65)
    if passed:
        logger.info("   BIGQUERY PIPELINE COMPLETED SUCCESSFULLY (EXIT 0)      ")
    else:
        logger.error("   BIGQUERY PIPELINE FAILED: GATES OR STAGES DID NOT PASS (EXIT 1) ")
        try:
            from pwa.observability.alerting import PipelineAlert, default_alert_sinks

            default_alert_sinks().send(
                PipelineAlert(
                    alert_type="PIPELINE_FAILURE",
                    severity="CRITICAL",
                    source_id="warehouse_pipeline",
                    table_name=None,
                    message="Warehouse build or BigQuery verification gates B1-B15 failed.",
                )
            )
        except Exception as alert_exc:
            logger.warning(f"Failed to dispatch warehouse failure alert: {alert_exc}")
    logger.info("=" * 65)

    return passed


if __name__ == "__main__":
    raise SystemExit(0 if run_warehouse_pipeline() else 1)
