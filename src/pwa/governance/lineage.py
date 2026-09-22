"""Internal lineage recording module for PWA.

Tracks source -> raw -> staging -> curated lineage for every pipeline execution.
Designed to interface with OpenLineage / Marquis standards in future releases.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
import pandas as pd

from pwa.settings import get_settings
from pwa.warehouse.bigquery.writer import BigQueryWriter

logger = logging.getLogger("pwa.governance.lineage")


class LineageTracker:
    """Internal lineage recorder tracking dataset transformations across pipeline layers."""

    def __init__(self, writer: Optional[BigQueryWriter] = None) -> None:
        settings = get_settings()
        self.dataset_id = settings.bq_ds_metadata
        self.writer = writer or BigQueryWriter()
        self.writer.create_dataset_if_not_exists(self.dataset_id)

    def record_lineage(
        self,
        run_id: str,
        source_system: str,
        source_table: str,
        raw_table: str,
        staging_table: Optional[str] = None,
        curated_table: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record lineage event for a dataset pipeline flow."""
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "run_id": run_id,
            "source_system": source_system,
            "source_table": source_table,
            "raw_table": raw_table,
            "staging_table": staging_table,
            "curated_table": curated_table,
            "recorded_at": now,
        }

        df = pd.DataFrame([record])
        self.writer.write_dataframe(df, self.dataset_id, "pwa_lineage", write_disposition="WRITE_APPEND")
        logger.info(
            f"[Lineage] `{run_id}`: {source_system}.{source_table} -> {raw_table} -> {staging_table} -> {curated_table}"
        )
        return record


class OpenLineageAdapter:
    """Adapter interface for emitting OpenLineage-compliant JSON run events."""

    def generate_openlineage_event(
        self,
        run_id: str,
        job_name: str,
        inputs: list[str],
        outputs: list[str],
        event_type: str = "COMPLETE",
    ) -> dict[str, Any]:
        """Produce an OpenLineage JSON specification payload."""
        now = datetime.now(timezone.utc).isoformat()
        return {
            "eventType": event_type.upper(),
            "eventTime": now,
            "run": {
                "runId": run_id,
            },
            "job": {
                "namespace": "pwa_nexora_platform",
                "name": job_name,
            },
            "inputs": [{"namespace": "bigquery", "name": inp} for inp in inputs],
            "outputs": [{"namespace": "bigquery", "name": out} for out in outputs],
            "producer": "https://github.com/Nexora/polyglot-warehouse-agent",
        }
