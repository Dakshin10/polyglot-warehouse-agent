"""Control-plane run metadata and operational state management.

Tracks run lifecycles, task execution status, row counts, errors,
and quality results without containing business data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
import pandas as pd

from pwa.observability.alerting import CompositeAlertSink, PipelineAlert, default_alert_sinks
from pwa.settings import get_settings
from pwa.warehouse.bigquery.writer import BigQueryWriter

logger = logging.getLogger("pwa.control_plane.metadata")


class ControlPlaneManager:
    """Manager for PWA control-plane operational metadata tables."""

    def __init__(
        self, writer: Optional[BigQueryWriter] = None, alert_sink: Optional[CompositeAlertSink] = None
    ) -> None:
        settings = get_settings()
        self.dataset_id = settings.bq_ds_metadata
        self.writer = writer or BigQueryWriter()
        self.writer.create_dataset_if_not_exists(self.dataset_id)
        self.alert_sink = alert_sink or default_alert_sinks()
        self._run_sources: dict[str, str] = {}  # run_id -> source_name, for alert context

    def start_pipeline_run(self, run_id: str, source_name: str, mode: str = "snapshot") -> dict[str, Any]:
        """Record the start of a pipeline run."""
        now = datetime.now(timezone.utc).isoformat()
        run_record = {
            "run_id": run_id,
            "source_name": source_name,
            "mode": mode,
            "status": "RUNNING",
            "started_at": now,
            "completed_at": None,
            "total_rows_extracted": 0,
            "total_rows_loaded": 0,
            "error_message": None,
        }

        df = pd.DataFrame([run_record])
        self.writer.write_dataframe(df, self.dataset_id, "pwa_pipeline_runs", write_disposition="WRITE_APPEND")
        logger.info(f"[ControlPlane] Run started: `{run_id}` for source `{source_name}`")
        self._run_sources[run_id] = source_name
        return run_record

    def finish_pipeline_run(
        self,
        run_id: str,
        status: str,
        total_rows_extracted: int = 0,
        total_rows_loaded: int = 0,
        error_message: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record completion of a pipeline run."""
        now = datetime.now(timezone.utc).isoformat()
        finish_record = {
            "run_id": run_id,
            "status": status,
            "completed_at": now,
            "total_rows_extracted": total_rows_extracted,
            "total_rows_loaded": total_rows_loaded,
            "error_message": error_message,
        }

        df = pd.DataFrame([finish_record])
        self.writer.write_dataframe(df, self.dataset_id, "pwa_pipeline_runs", write_disposition="WRITE_APPEND")
        logger.info(
            f"[ControlPlane] Run finished: `{run_id}` -> {status} (extracted={total_rows_extracted}, loaded={total_rows_loaded})"
        )

        if status not in ("SUCCESS", "RUNNING"):
            self.alert_sink.send(
                PipelineAlert(
                    alert_type="PIPELINE_FAILURE",
                    severity="HIGH",
                    source_id=self._run_sources.get(run_id, "unknown"),
                    table_name=None,
                    run_id=run_id,
                    message=error_message or f"Pipeline run `{run_id}` finished with status {status}.",
                )
            )

        return finish_record

    def record_task_execution(
        self,
        run_id: str,
        task_name: str,
        status: str,
        table_name: Optional[str] = None,
        rows_affected: int = 0,
        error_message: Optional[str] = None,
    ) -> None:
        """Record individual task execution lifecycle."""
        now = datetime.now(timezone.utc).isoformat()
        task_record = {
            "run_id": run_id,
            "task_name": task_name,
            "table_name": table_name,
            "status": status,
            "executed_at": now,
            "rows_affected": rows_affected,
            "error_message": error_message,
        }
        df = pd.DataFrame([task_record])
        self.writer.write_dataframe(df, self.dataset_id, "pwa_task_execution", write_disposition="WRITE_APPEND")

    def record_quality_result(
        self,
        run_id: str,
        source_id: str,
        table_name: str,
        gate_name: str,
        status: str,
        message: str = "",
        metrics: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record quality gate result."""
        now = datetime.now(timezone.utc).isoformat()
        q_record = {
            "run_id": run_id,
            "source_id": source_id,
            "table_name": table_name,
            "gate_name": gate_name,
            "status": status,
            "message": message,
            "metrics": str(metrics) if metrics else None,
            "evaluated_at": now,
        }
        df = pd.DataFrame([q_record])
        self.writer.write_dataframe(df, self.dataset_id, "pwa_quality_results", write_disposition="WRITE_APPEND")

        if status == "FAIL":
            self.alert_sink.send(
                PipelineAlert(
                    alert_type="QUALITY_FAILURE",
                    severity="HIGH",
                    source_id=source_id,
                    table_name=table_name,
                    run_id=run_id,
                    message=message or f"Quality gate `{gate_name}` failed.",
                )
            )

    def record_audit_log(
        self,
        event_type: str,
        message: str,
        source_name: Optional[str] = None,
        table_name: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> None:
        """Record an append-only operational audit log entry into BigQuery `pwa_audit_log`.

        Security Posture & Immutability Architecture:
        1. App-Layer: Writes strictly append-only entries (WRITE_APPEND).
        2. IAM Scoping: Application service accounts should be restricted to append-only
           grants on `pwa_metadata.pwa_audit_log` (without delete/update permissions).
        3. Regulatory Compliance (SOC2/HIPAA): Enterprise deployments should route
           Google Cloud Audit Logs (Admin & Data Access) to a SIEM / GCS bucket
           configured with WORM (Write Once Read Many) retention lock.
        """
        now = datetime.now(timezone.utc).isoformat()
        audit_record = {
            "timestamp": now,
            "event_type": event_type,
            "source_name": source_name,
            "table_name": table_name,
            "run_id": run_id,
            "message": message,
        }
        df = pd.DataFrame([audit_record])
        self.writer.write_dataframe(df, self.dataset_id, "pwa_audit_log", write_disposition="WRITE_APPEND")

    def get_recent_audit_logs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Retrieve recent audit log records."""
        try:
            df = self.writer.get_table_dataframe(self.dataset_id, "pwa_audit_log")
            if df.empty:
                return []
            return df.tail(limit).to_dict(orient="records")
        except Exception:
            return []

    def get_last_successful_ingestion(self, source_name: str) -> Optional[str]:
        """Return the completion timestamp of the most recent SUCCESS run for a source.

        Returns None if there is no recorded successful run (or the lookup
        fails) — callers should treat that as "freshness unknown", not "stale".
        """
        try:
            df = self.writer.get_table_dataframe(self.dataset_id, "pwa_pipeline_runs")
            if df.empty:
                return None
            matches = df[(df["source_name"] == source_name) & (df["status"] == "SUCCESS") & df["completed_at"].notna()]
            if matches.empty:
                return None
            return str(matches["completed_at"].max())
        except Exception as exc:
            logger.debug(f"[ControlPlane] Could not look up last successful ingestion for `{source_name}`: {exc}")
            return None

    def get_latest_quality_status(self, source_id: str, table_name: str) -> str:
        """Return PASS/FAIL/UNKNOWN from the most recent gate result recorded per gate.

        FAIL if any gate's latest recorded result for this table is FAIL,
        PASS if every recorded gate's latest result passed, UNKNOWN if there
        is no recorded quality-gate history for this table at all.
        """
        try:
            df = self.writer.get_table_dataframe(self.dataset_id, "pwa_quality_results")
            if df.empty:
                return "UNKNOWN"
            matches = df[(df["source_id"] == source_id) & (df["table_name"] == table_name)]
            if matches.empty:
                return "UNKNOWN"
            latest_per_gate = matches.sort_values("evaluated_at").groupby("gate_name").tail(1)
            return "FAIL" if (latest_per_gate["status"] == "FAIL").any() else "PASS"
        except Exception as exc:
            logger.debug(f"[ControlPlane] Could not look up quality status for `{source_id}.{table_name}`: {exc}")
            return "UNKNOWN"
