"""Control plane / metadata setup for the Nexora enterprise data platform.

Creates and manages the pwa_metadata BigQuery dataset and its control tables:
  - pwa_sources           — registered source system catalog
  - pwa_source_tables     — source table registry
  - pwa_pipeline_runs     — ingestion run history
  - pwa_watermarks        — per-table high-water marks
  - pwa_schema_versions   — schema evolution log
  - pwa_quality_results   — quality gate results per run
  - pwa_audit_log         — immutable audit trail

All control tables are created idempotently.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from google.cloud import bigquery

from pwa.connections import get_bq_client
from pwa.settings import get_settings

logger = logging.getLogger("pwa.pwa_metadata_setup")

# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

CONTROL_TABLES: dict[str, list[bigquery.SchemaField]] = {
    "pwa_sources": [
        bigquery.SchemaField("source_name", "STRING", mode="REQUIRED", description="Unique source system name"),
        bigquery.SchemaField("source_type", "STRING", description="file | database"),
        bigquery.SchemaField("provider", "STRING", description="kaggle | mysql | postgres"),
        bigquery.SchemaField("kaggle_slug", "STRING", description="Kaggle dataset slug if provider=kaggle"),
        bigquery.SchemaField("source_url", "STRING", description="URL to upstream source"),
        bigquery.SchemaField("domain", "STRING", description="enterprise | marketplace | marketing"),
        bigquery.SchemaField("license", "STRING", description="Dataset license identifier"),
        bigquery.SchemaField("bq_raw_dataset", "STRING", description="Target BigQuery raw dataset"),
        bigquery.SchemaField("registered_at", "TIMESTAMP", description="When source was registered"),
        bigquery.SchemaField("is_active", "BOOL", description="Whether source is active"),
    ],
    "pwa_source_tables": [
        bigquery.SchemaField("source_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("table_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("primary_key", "STRING", description="PK column(s), comma-separated"),
        bigquery.SchemaField("watermark_column", "STRING", description="Incremental watermark column"),
        bigquery.SchemaField("source_file_pattern", "STRING"),
        bigquery.SchemaField("bq_raw_table", "STRING", description="Target BigQuery raw table"),
        bigquery.SchemaField("registered_at", "TIMESTAMP"),
    ],
    "pwa_pipeline_runs": [
        bigquery.SchemaField("run_id", "STRING", mode="REQUIRED", description="UUID for this pipeline run"),
        bigquery.SchemaField("source_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("pipeline_stage", "STRING", description="download | raw | staging | curated | quality"),
        bigquery.SchemaField("started_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("completed_at", "TIMESTAMP"),
        bigquery.SchemaField("status", "STRING", description="running | success | failed | partial"),
        bigquery.SchemaField("rows_read", "INTEGER"),
        bigquery.SchemaField("rows_written", "INTEGER"),
        bigquery.SchemaField("error_message", "STRING"),
        bigquery.SchemaField("triggered_by", "STRING", description="cli | schedule | api"),
    ],
    "pwa_watermarks": [
        bigquery.SchemaField("source_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("table_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("watermark_column", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("last_value", "STRING", description="String representation of last successful watermark"),
        bigquery.SchemaField("last_value_type", "STRING", description="timestamp | date | integer | string"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("run_id", "STRING", description="Run that advanced this watermark"),
    ],
    "pwa_schema_versions": [
        bigquery.SchemaField("source_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("table_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("version", "INTEGER", mode="REQUIRED", description="Monotonically increasing version"),
        bigquery.SchemaField("schema_hash", "STRING", description="SHA-256 of column list+types"),
        bigquery.SchemaField("columns_added", "JSON", description="Columns added vs previous version"),
        bigquery.SchemaField("columns_removed", "JSON", description="Columns removed vs previous version"),
        bigquery.SchemaField("type_changes", "JSON", description="Type changes vs previous version"),
        bigquery.SchemaField("evolution_action", "STRING", description="allow | warn | block"),
        bigquery.SchemaField("recorded_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("run_id", "STRING"),
    ],
    "pwa_quality_results": [
        bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("table_name", "STRING"),
        bigquery.SchemaField("gate_id", "STRING", mode="REQUIRED", description="Gate identifier e.g. G1, B1"),
        bigquery.SchemaField("gate_name", "STRING", description="Human-readable gate description"),
        bigquery.SchemaField("gate_layer", "STRING", description="source | bigquery | staging | curated"),
        bigquery.SchemaField("passed", "BOOL", mode="REQUIRED"),
        bigquery.SchemaField("detail", "STRING", description="Result detail or failure reason"),
        bigquery.SchemaField("is_mutating", "BOOL"),
        bigquery.SchemaField("cannot_verify", "BOOL"),
        bigquery.SchemaField("evaluated_at", "TIMESTAMP", mode="REQUIRED"),
    ],
    "pwa_audit_log": [
        bigquery.SchemaField("event_id", "STRING", mode="REQUIRED", description="UUID for this audit event"),
        bigquery.SchemaField(
            "event_type",
            "STRING",
            mode="REQUIRED",
            description="ingestion | quality_gate | schema_change | watermark | deletion | query",
        ),
        bigquery.SchemaField("source_name", "STRING"),
        bigquery.SchemaField("table_name", "STRING"),
        bigquery.SchemaField("run_id", "STRING"),
        bigquery.SchemaField("actor", "STRING", description="User, SA, or service that triggered the event"),
        bigquery.SchemaField("event_detail", "JSON", description="Event-specific payload as JSON"),
        bigquery.SchemaField("severity", "STRING", description="INFO | WARNING | ERROR"),
        bigquery.SchemaField("occurred_at", "TIMESTAMP", mode="REQUIRED"),
    ],
}


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------


def create_metadata_tables(client: bigquery.Client, project: str) -> None:
    """Create all pwa_metadata control tables idempotently."""
    s = get_settings()
    ds_id = s.bq_ds_metadata
    full_ds = f"{project}.{ds_id}"

    for table_name, schema in CONTROL_TABLES.items():
        table_ref = f"{full_ds}.{table_name}"
        table = bigquery.Table(table_ref, schema=schema)

        try:
            client.create_table(table, exists_ok=True)
            logger.info(f"Control table ready: `{table_ref}`")
        except Exception as e:
            logger.error(f"Failed to create control table `{table_ref}`: {e}")
            raise

    logger.info(f"All {len(CONTROL_TABLES)} control tables ready in `{full_ds}`.")


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_sources_in_metadata(client: bigquery.Client, project: str) -> None:
    """Write source and table registry entries to pwa_metadata."""
    from pwa.source_registry import load_registry

    s = get_settings()
    ds_id = s.bq_ds_metadata
    now = datetime.now(timezone.utc).isoformat()

    registry = load_registry()

    # Upsert source rows
    source_rows = []
    for src in registry.sources:
        source_rows.append(
            {
                "source_name": src.name,
                "source_type": src.type,
                "provider": src.provider,
                "kaggle_slug": src.slug,
                "source_url": src.source_url,
                "domain": src.domain,
                "license": src.license,
                "bq_raw_dataset": src.bq_raw_dataset,
                "registered_at": now,
                "is_active": True,
            }
        )

    table_rows = []
    for src in registry.sources:
        for tbl in src.tables:
            table_rows.append(
                {
                    "source_name": src.name,
                    "table_name": tbl.name,
                    "primary_key": tbl.primary_key,
                    "watermark_column": tbl.watermark_column,
                    "source_file_pattern": tbl.source_file_pattern,
                    "bq_raw_table": f"{src.bq_raw_dataset}.{tbl.name}",
                    "registered_at": now,
                }
            )

    # Truncate and reload (idempotent registration)
    _load_rows(client, f"{project}.{ds_id}.pwa_sources", source_rows, "WRITE_TRUNCATE")
    _load_rows(client, f"{project}.{ds_id}.pwa_source_tables", table_rows, "WRITE_TRUNCATE")

    logger.info(f"Registered {len(source_rows)} source(s) and {len(table_rows)} table(s) in pwa_metadata.")


def _load_rows(client: bigquery.Client, table_ref: str, rows: list[dict], write_disposition: str) -> None:
    if not rows:
        return
    job_config = bigquery.LoadJobConfig(
        write_disposition=write_disposition,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    job = client.load_table_from_json(rows, table_ref, job_config=job_config)
    job.result()


# ---------------------------------------------------------------------------
# Run tracking helpers
# ---------------------------------------------------------------------------


def start_pipeline_run(
    source_name: str,
    stage: str,
    triggered_by: str = "cli",
) -> str:
    """Record the start of a pipeline run. Returns the run_id."""
    client = get_bq_client()
    s = get_settings()
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    rows = [
        {
            "run_id": run_id,
            "source_name": source_name,
            "pipeline_stage": stage,
            "started_at": now,
            "status": "running",
            "triggered_by": triggered_by,
        }
    ]
    _load_rows(client, f"{s.gcp_project}.{s.bq_ds_metadata}.pwa_pipeline_runs", rows, "WRITE_APPEND")
    logger.info(f"Pipeline run started: run_id={run_id}, source={source_name}, stage={stage}")
    return run_id


def complete_pipeline_run(
    run_id: str,
    source_name: str,
    stage: str,
    status: str,
    rows_read: Optional[int] = None,
    rows_written: Optional[int] = None,
    error_message: Optional[str] = None,
) -> None:
    """Update an existing pipeline run record with completion status.

    Uses an INSERT (append) with a SELECT DISTINCT in a subsequent merge.
    For simplicity, appends a completion row; queries should use MAX(started_at).
    """
    client = get_bq_client()
    s = get_settings()
    now = datetime.now(timezone.utc).isoformat()

    rows = [
        {
            "run_id": run_id,
            "source_name": source_name,
            "pipeline_stage": stage,
            "started_at": now,
            "completed_at": now,
            "status": status,
            "rows_read": rows_read,
            "rows_written": rows_written,
            "error_message": error_message,
        }
    ]
    _load_rows(client, f"{s.gcp_project}.{s.bq_ds_metadata}.pwa_pipeline_runs", rows, "WRITE_APPEND")
    logger.info(f"Pipeline run completed: run_id={run_id}, status={status}")


def record_quality_result(
    run_id: str,
    source_name: str,
    gate_id: str,
    gate_name: str,
    gate_layer: str,
    passed: bool,
    detail: str = "",
    table_name: Optional[str] = None,
    is_mutating: bool = False,
    cannot_verify: bool = False,
) -> None:
    """Append a quality gate result to pwa_quality_results."""
    client = get_bq_client()
    s = get_settings()

    rows = [
        {
            "run_id": run_id,
            "source_name": source_name,
            "table_name": table_name,
            "gate_id": gate_id,
            "gate_name": gate_name,
            "gate_layer": gate_layer,
            "passed": passed,
            "detail": detail,
            "is_mutating": is_mutating,
            "cannot_verify": cannot_verify,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
    ]
    _load_rows(client, f"{s.gcp_project}.{s.bq_ds_metadata}.pwa_quality_results", rows, "WRITE_APPEND")


def advance_watermark(
    source_name: str,
    table_name: str,
    watermark_column: str,
    new_value: str,
    value_type: str,
    run_id: str,
) -> None:
    """Record a new watermark value. ONLY call after successful warehouse commit.

    Invariant: watermark advances only after extraction, quality validation,
    and warehouse commit all succeed.
    """
    client = get_bq_client()
    s = get_settings()

    rows = [
        {
            "source_name": source_name,
            "table_name": table_name,
            "watermark_column": watermark_column,
            "last_value": str(new_value),
            "last_value_type": value_type,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
        }
    ]
    _load_rows(client, f"{s.gcp_project}.{s.bq_ds_metadata}.pwa_watermarks", rows, "WRITE_APPEND")
    logger.info(f"Watermark advanced: {source_name}.{table_name}.{watermark_column} = {new_value}")


def get_current_watermark(source_name: str, table_name: str, watermark_column: str) -> Optional[str]:
    """Retrieve the most recent watermark value for a table."""
    client = get_bq_client()
    s = get_settings()

    sql = f"""
    SELECT last_value
    FROM `{s.gcp_project}.{s.bq_ds_metadata}.pwa_watermarks`
    WHERE source_name = @source
      AND table_name = @table
      AND watermark_column = @col
    ORDER BY updated_at DESC
    LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("source", "STRING", source_name),
            bigquery.ScalarQueryParameter("table", "STRING", table_name),
            bigquery.ScalarQueryParameter("col", "STRING", watermark_column),
        ]
    )
    try:
        rows = list(client.query(sql, job_config=job_config).result())
        return rows[0]["last_value"] if rows else None
    except Exception as e:
        logger.warning(f"Could not retrieve watermark for {source_name}.{table_name}: {e}")
        return None


def write_audit_event(
    event_type: str,
    actor: str = "pwa-pipeline",
    source_name: Optional[str] = None,
    table_name: Optional[str] = None,
    run_id: Optional[str] = None,
    severity: str = "INFO",
    detail: Optional[dict] = None,
) -> None:
    """Append an immutable audit event to pwa_audit_log."""
    client = get_bq_client()
    s = get_settings()

    rows = [
        {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "source_name": source_name,
            "table_name": table_name,
            "run_id": run_id,
            "actor": actor,
            "event_detail": json.dumps(detail or {}),
            "severity": severity,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
    ]
    _load_rows(client, f"{s.gcp_project}.{s.bq_ds_metadata}.pwa_audit_log", rows, "WRITE_APPEND")


# ---------------------------------------------------------------------------
# Full metadata setup
# ---------------------------------------------------------------------------


def run_metadata_setup() -> bool:
    """Create all pwa_metadata tables and register sources."""
    s = get_settings()
    project = s.gcp_project
    client = get_bq_client()

    logger.info("=== SETTING UP PWA METADATA CONTROL PLANE ===")
    create_metadata_tables(client, project)

    logger.info("=== REGISTERING SOURCES IN METADATA ===")
    register_sources_in_metadata(client, project)

    logger.info("=== PWA METADATA SETUP COMPLETE ===")
    return True


if __name__ == "__main__":
    from pwa.logging_setup import setup_logging

    setup_logging()
    raise SystemExit(0 if run_metadata_setup() else 1)
