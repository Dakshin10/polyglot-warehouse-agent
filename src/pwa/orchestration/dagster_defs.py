"""Dagster asset graph for the PWA data pipeline.

Run locally:
    dagster dev -m pwa.orchestration.dagster_defs

Deploy anywhere Dagster runs (Dagster+, an OSS Dagster instance on GKE/ECS,
etc.) the same way as any other Dagster project — this module only needs to
be importable, it starts no infrastructure of its own.

Asset graph
-----------
source_ingestion -> source_quality_gates -> warehouse_build -> warehouse_quality_gates -> rollup_refresh

Each asset calls the exact same function the `pwa` CLI already calls
(`run_source_pipeline`, `run_all_gates`, `run_warehouse_pipeline`,
`run_all_bq_gates`, `refresh_rollups`) — this is a scheduling and retry layer
on top of existing, already-tested logic, not a rewrite of it.

Retries: transient failures (a flaky source DB connection, a momentary BQ
quota blip) are retried automatically with backoff. A failure that survives
all retries fails the run and — via `pipeline_failure_sensor` below — posts
to the same alert sinks the rest of the platform uses (Slack/PagerDuty/log),
instead of silently sitting red in a UI nobody is watching at 3am.
"""

from dagster import (
    AssetExecutionContext,
    AssetSelection,
    Definitions,
    RetryPolicy,
    RunFailureSensorContext,
    ScheduleDefinition,
    asset,
    define_asset_job,
    run_failure_sensor,
)

_TRANSIENT_RETRY = RetryPolicy(max_retries=2, delay=30.0, backoff=None)


@asset(retry_policy=_TRANSIENT_RETRY)
def source_ingestion(context: AssetExecutionContext) -> bool:
    """Download -> transform -> load every registered source (`pwa source run`)."""
    from pwa.run_source import run_source_pipeline

    ok = run_source_pipeline()
    if not ok:
        raise RuntimeError("Source ingestion pipeline reported failure — see logs above for the failing source.")
    context.log.info("Source ingestion completed successfully.")
    return ok


@asset(deps=[source_ingestion], retry_policy=_TRANSIENT_RETRY)
def source_quality_gates(context: AssetExecutionContext) -> bool:
    """Gates 1-13 against freshly-ingested raw data (`pwa source verify`)."""
    from pwa.gates_source import run_all_gates

    ok = run_all_gates()
    if not ok:
        raise RuntimeError("One or more source quality gates (1-13) failed — do not proceed to warehouse build.")
    context.log.info("Source quality gates 1-13 passed.")
    return ok


@asset(deps=[source_quality_gates], retry_policy=_TRANSIENT_RETRY)
def warehouse_build(context: AssetExecutionContext) -> bool:
    """Stage -> curate -> mart build (`pwa warehouse run`)."""
    from pwa.run_bigquery import run_warehouse_pipeline

    ok = run_warehouse_pipeline()
    if not ok:
        raise RuntimeError("Warehouse build pipeline (staging/curated/mart) reported failure.")
    context.log.info("Warehouse build completed successfully.")
    return ok


@asset(deps=[warehouse_build], retry_policy=_TRANSIENT_RETRY)
def warehouse_quality_gates(context: AssetExecutionContext) -> bool:
    """Gates B1-B15 against the built warehouse (`pwa warehouse verify`)."""
    from pwa.gates_bigquery import run_all_bq_gates

    ok = run_all_bq_gates()
    if not ok:
        raise RuntimeError("One or more warehouse quality gates (B1-B15) failed.")
    context.log.info("Warehouse quality gates B1-B15 passed.")
    return ok


@asset(deps=[warehouse_quality_gates], retry_policy=_TRANSIENT_RETRY)
def rollup_refresh(context: AssetExecutionContext) -> bool:
    """Recompute the fast-path rollup tables (`pwa refresh-rollups`)."""
    from pwa.rollups import refresh_rollups

    ok = refresh_rollups()
    if not ok:
        raise RuntimeError("Rollup materialization failed.")
    context.log.info("Rollup tables refreshed successfully.")
    return ok


@asset(deps=[warehouse_quality_gates], retry_policy=_TRANSIENT_RETRY)
def periodic_reconciliation(context: AssetExecutionContext) -> bool:
    """Periodic full PK set reconciliation to detect deleted rows across operational sources."""
    from pwa.quality.reconciliation import run_full_reconciliation

    ok = run_full_reconciliation()
    if not ok:
        raise RuntimeError("Periodic full PK reconciliation reported failure.")
    context.log.info("Periodic full PK reconciliation completed successfully.")
    return ok


full_pipeline_job = define_asset_job(
    name="full_pipeline_job",
    selection=AssetSelection.assets(
        source_ingestion,
        source_quality_gates,
        warehouse_build,
        warehouse_quality_gates,
        rollup_refresh,
    ),
    description="source_ingestion -> source_quality_gates -> warehouse_build -> warehouse_quality_gates -> rollup_refresh",
)

reconciliation_job = define_asset_job(
    name="reconciliation_job",
    selection=AssetSelection.assets(periodic_reconciliation),
    description="Full PK set reconciliation job to detect and purge deleted rows across operational sources.",
)

# Daily at 02:00 UTC by default — override the cron in your Dagster deployment
# config rather than editing this file per-environment.
daily_pipeline_schedule = ScheduleDefinition(
    job=full_pipeline_job,
    cron_schedule="0 2 * * *",
)

daily_reconciliation_schedule = ScheduleDefinition(
    job=reconciliation_job,
    cron_schedule="0 3 * * *",
)


@run_failure_sensor(monitored_jobs=[full_pipeline_job, reconciliation_job])
def pipeline_failure_sensor(context: RunFailureSensorContext) -> None:
    """Fan a Dagster run failure out to the platform's own alert sinks
    (Slack/PagerDuty/log — see pwa.observability.alerting) instead of only
    being visible to someone who happens to have the Dagster UI open."""
    from pwa.observability.alerting import PipelineAlert, default_alert_sinks

    default_alert_sinks().send(
        PipelineAlert(
            alert_type="PIPELINE_FAILURE",
            severity="CRITICAL",
            source_id="dagster",
            table_name=None,
            run_id=context.dagster_run.run_id,
            message=f"Dagster job `{context.dagster_run.job_name}` failed: {context.failure_event.message}",
        )
    )


defs = Definitions(
    assets=[
        source_ingestion,
        source_quality_gates,
        warehouse_build,
        warehouse_quality_gates,
        rollup_refresh,
        periodic_reconciliation,
    ],
    jobs=[full_pipeline_job, reconciliation_job],
    schedules=[daily_pipeline_schedule, daily_reconciliation_schedule],
    sensors=[pipeline_failure_sensor],
)

