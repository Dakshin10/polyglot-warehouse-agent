"""Watermark state manager enforcing strict transactional watermark invariants."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
import pandas as pd

from pwa.settings import get_settings
from pwa.warehouse.bigquery.writer import BigQueryWriter

logger = logging.getLogger("pwa.control_plane.watermark")


class WatermarkManager:
    """Manages source table watermark state in pwa_watermarks table.

    Mandatory Invariant:
      WATERMARK MAY ADVANCE ONLY AFTER extraction, transformation,
      quality checks, warehouse commit, and reconciliation ALL succeed.
      If any stage fails, the previous watermark is strictly preserved.
    """

    def __init__(self, writer: Optional[BigQueryWriter] = None) -> None:
        settings = get_settings()
        self.dataset_id = settings.bq_ds_metadata
        self.writer = writer or BigQueryWriter()
        self.writer.create_dataset_if_not_exists(self.dataset_id)
        self._memory_watermarks: dict[str, str] = {}

    def get_watermark(self, source_id: str, table_name: str) -> Optional[str]:
        """Get the current active watermark value for a table."""
        key = f"{source_id}.{table_name}"
        if key in self._memory_watermarks:
            return self._memory_watermarks[key]

        df = self.writer.get_table_dataframe(self.dataset_id, "pwa_watermarks")
        if df.empty or "source_id" not in df.columns:
            return None

        filtered = df[(df["source_id"] == source_id) & (df["table_name"] == table_name)]
        if filtered.empty:
            return None

        # Return the latest successful new_watermark
        val = str(filtered.sort_values("updated_at", ascending=False)["new_watermark"].iloc[0])
        self._memory_watermarks[key] = val
        return val

    def advance_watermark(
        self,
        source_id: str,
        table_name: str,
        watermark_col: str,
        new_watermark: Any,
        run_id: str,
        extraction_ok: bool,
        transformation_ok: bool,
        quality_ok: bool,
        commit_ok: bool,
        reconciliation_ok: bool = True,
    ) -> bool:
        """Advance watermark ONLY IF all 5 required stages succeeded."""
        key = f"{source_id}.{table_name}"
        previous_wm = self.get_watermark(source_id, table_name)

        stages_ok = extraction_ok and transformation_ok and quality_ok and commit_ok and reconciliation_ok

        if not stages_ok:
            failed_stages = []
            if not extraction_ok:
                failed_stages.append("extraction")
            if not transformation_ok:
                failed_stages.append("transformation")
            if not quality_ok:
                failed_stages.append("quality_checks")
            if not commit_ok:
                failed_stages.append("warehouse_commit")
            if not reconciliation_ok:
                failed_stages.append("reconciliation")

            logger.warning(
                f"[Watermark INVARIANT PRESERVED] Watermark NOT advanced for `{key}` "
                f"due to failed stage(s): {failed_stages}. Preserving previous watermark: '{previous_wm}'"
            )
            return False

        now = datetime.now(timezone.utc).isoformat()
        new_wm_str = str(new_watermark)

        record = {
            "source_id": source_id,
            "table_name": table_name,
            "watermark_column": watermark_col,
            "previous_watermark": previous_wm,
            "new_watermark": new_wm_str,
            "updated_at": now,
            "run_id": run_id,
            "status": "ADVANCED",
        }

        df = pd.DataFrame([record])
        self.writer.write_dataframe(df, self.dataset_id, "pwa_watermarks", write_disposition="WRITE_APPEND")
        self._memory_watermarks[key] = new_wm_str

        logger.info(f"✓ [Watermark ADVANCED] `{key}`: '{previous_wm}' -> '{new_wm_str}' (run_id={run_id})")
        return True
