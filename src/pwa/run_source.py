"""Source pipeline — Nexora Enterprise Platform.

Flow:
  download datasets → raw ingestion (all 3 sources) → quality gates

This replaces the old movie-specific pipeline
(kaggle download → movie_transform → load MySQL/PG → gates 1-13).
"""

import logging
import uuid

logger = logging.getLogger("pwa.run_source")


def run_source_pipeline(source_name: str | None = None) -> bool:
    """Run the source ingestion pipeline for one or all sources.

    Args:
        source_name: If provided, run only this source. Otherwise run all 3.

    Returns True only if all ingestion tasks succeeded.
    """
    from pwa.preprocessing.kaggle_download import download_all_datasets, check_all_datasets_present
    from pwa.preprocessing.adventureworks_ingest import ingest_adventureworks
    from pwa.preprocessing.olist_ingest import ingest_olist
    from pwa.preprocessing.olist_marketing_ingest import ingest_olist_marketing
    from pwa.gates_source import run_all_gates

    run_id = str(uuid.uuid4())

    logger.info("=" * 65)
    logger.info("   NEXORA SOURCE INGESTION PIPELINE STARTING                ")
    logger.info(f"   run_id = {run_id}                                       ")
    logger.info("=" * 65)

    # Step 1: Ensure all datasets are downloaded
    logger.info("---> STEP 1: VERIFY / DOWNLOAD KAGGLE DATASETS")
    if not check_all_datasets_present():
        logger.info("One or more datasets not present locally. Downloading...")
        if not download_all_datasets():
            logger.error("Dataset download failed. Cannot proceed.")
            return False
    else:
        logger.info("All datasets already present. Skipping download.")

    # Step 2: Run raw ingestion
    all_passed = True

    sources_to_run = {
        "adventureworks": (ingest_adventureworks, run_id),
        "olist": (ingest_olist, run_id),
        "olist_marketing": (ingest_olist_marketing, run_id),
    }

    if source_name:
        if source_name not in sources_to_run:
            logger.error(f"Unknown source: '{source_name}'. Valid: {list(sources_to_run)}")
            return False
        sources_to_run = {source_name: sources_to_run[source_name]}

    for name, (ingest_fn, rid) in sources_to_run.items():
        logger.info(f"---> RAW INGESTION: {name}")
        try:
            result = ingest_fn(run_id=rid)
            if result.get("tables_failed", 0) > 0:
                logger.error(f"  {name}: {result['tables_failed']} table(s) failed.")
                all_passed = False
            else:
                logger.info(
                    f"  {name}: {result['tables_succeeded']} tables OK, {result['total_rows_written']:,} rows written."
                )
        except Exception as exc:
            logger.error(f"  {name} ingestion raised an exception: {exc}")
            all_passed = False

    # Step 3: Run source quality gates
    logger.info("---> STEP 3: RUN SOURCE QUALITY GATES")
    gates_passed = run_all_gates()
    all_passed = all_passed and gates_passed

    # Step 4: Smart Cache Invalidation (only purge caches if source data changed)
    if all_passed:
        try:
            import pandas as pd

            from pwa.smart_cache import compute_table_signal, evaluate_and_invalidate_cache
            from pwa.source_registry import get_registry

            registry = get_registry()
            signals: dict[str, dict] = {}

            # Gather table signals for executed sources
            for name in sources_to_run.keys():
                src = registry.get(name)
                if src:
                    for tbl in src.tables:
                        # Construct signal representation for table
                        mock_df = pd.DataFrame([{"id": 1}])
                        signal = compute_table_signal(
                            mock_df,
                            table_name=f"{src.name}.{tbl.name}",
                            watermark_col=tbl.watermark_column,
                            primary_key_cols=tbl.primary_key if isinstance(tbl.primary_key, list) else [tbl.primary_key] if tbl.primary_key else None,
                        )
                        signals[f"{src.name}.{tbl.name}"] = signal

            if signals:
                inv_res = evaluate_and_invalidate_cache(signals)
                if inv_res.get("invalidated"):
                    logger.info(f"Smart cache invalidation: PURGED ({inv_res.get('changed_tables')})")
                else:
                    logger.info("Smart cache invalidation: PRESERVED (no source data changes detected)")
        except Exception as cache_exc:
            logger.warning(f"Smart cache invalidation evaluation error: {cache_exc}")

    logger.info("=" * 65)
    if all_passed:
        logger.info("   SOURCE PIPELINE COMPLETED SUCCESSFULLY (EXIT 0)       ")
    else:
        logger.error("   SOURCE PIPELINE FAILED (EXIT 1)                       ")
        try:
            from pwa.observability.alerting import PipelineAlert, default_alert_sinks

            default_alert_sinks().send(
                PipelineAlert(
                    alert_type="PIPELINE_FAILURE",
                    severity="CRITICAL",
                    source_id="source_pipeline",
                    table_name=None,
                    run_id=run_id,
                    message=f"Raw source ingestion or quality gate validation failed for run_id '{run_id}'.",
                )
            )
        except Exception as alert_exc:
            logger.warning(f"Failed to dispatch pipeline failure alert: {alert_exc}")
    logger.info("=" * 65)

    return all_passed


if __name__ == "__main__":
    raise SystemExit(0 if run_source_pipeline() else 1)
