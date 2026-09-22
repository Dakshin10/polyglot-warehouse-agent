"""Schema evolution and drift detection engine for PWA.

Policy Rules:
- NEW COLUMN -> ALLOW + log
- WIDER COMPATIBLE TYPE -> ALLOW + log
- INCOMPATIBLE TYPE -> BLOCK
- PRIMARY KEY CHANGE -> BLOCK
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
import pandas as pd

from pwa.ingestion.connectors.base import TableSchema
from pwa.settings import get_settings
from pwa.warehouse.bigquery.writer import BigQueryWriter

logger = logging.getLogger("pwa.governance.schema_evolution")

# Compatible type widening map
COMPATIBLE_TYPE_WIDENING = {
    "integer": {"bigint", "numeric", "real", "float", "text", "varchar", "string"},
    "int": {"bigint", "integer", "numeric", "real", "float", "text", "varchar", "string"},
    "smallint": {"int", "integer", "bigint", "numeric", "text", "varchar", "string"},
    "float": {"double", "numeric", "text", "varchar", "string"},
    "real": {"double", "numeric", "text", "varchar", "string"},
}


class SchemaEvolutionEngine:
    """Engine for schema discovery, drift detection, and version control."""

    def __init__(self, writer: Optional[BigQueryWriter] = None) -> None:
        settings = get_settings()
        self.dataset_id = settings.bq_ds_metadata
        self.writer = writer or BigQueryWriter()
        self.writer.create_dataset_if_not_exists(self.dataset_id)

    def evaluate_schema_change(
        self,
        source_id: str,
        table_name: str,
        current_schema: TableSchema,
        previous_schema: Optional[TableSchema] = None,
        run_id: str = "init",
    ) -> dict[str, Any]:
        """Evaluate schema changes between previous and current schema definitions."""
        result: dict[str, Any] = {
            "source_id": source_id,
            "table_name": table_name,
            "status": "ALLOWED",  # ALLOWED | BLOCKED
            "changes": [],
            "warnings": [],
            "errors": [],
        }

        if previous_schema is None:
            logger.info(
                f"[{source_id}.{table_name}] Initial schema registered ({len(current_schema.columns)} columns)."
            )
            self._save_version(source_id, table_name, current_schema, version=1, run_id=run_id)
            return result

        # Check Primary Key changes
        if set(current_schema.primary_key) != set(previous_schema.primary_key):
            msg = f"Primary key change blocked: previous={previous_schema.primary_key}, current={current_schema.primary_key}"
            logger.error(f"[{source_id}.{table_name}] {msg}")
            result["status"] = "BLOCKED"
            result["errors"].append(msg)

        prev_col_map = {c.name.lower(): c for c in previous_schema.columns}

        for curr_col in current_schema.columns:
            c_name = curr_col.name.lower()
            if c_name not in prev_col_map:
                msg = f"New column detected: '{curr_col.name}' ({curr_col.data_type}) -> ALLOWED"
                logger.info(f"[{source_id}.{table_name}] {msg}")
                result["changes"].append(msg)
            else:
                prev_col = prev_col_map[c_name]
                p_type = prev_col.data_type.lower()
                c_type = curr_col.data_type.lower()

                if p_type != c_type:
                    # Check compatible widening
                    allowed_widening = COMPATIBLE_TYPE_WIDENING.get(p_type, set())
                    if c_type in allowed_widening:
                        msg = f"Wider compatible type widening: '{curr_col.name}' ({p_type} -> {c_type}) -> ALLOWED"
                        logger.info(f"[{source_id}.{table_name}] {msg}")
                        result["changes"].append(msg)
                    else:
                        msg = f"Incompatible type change: '{curr_col.name}' ({p_type} -> {c_type}) -> BLOCKED"
                        logger.error(f"[{source_id}.{table_name}] {msg}")
                        result["status"] = "BLOCKED"
                        result["errors"].append(msg)

        if result["status"] == "ALLOWED":
            self._save_version(source_id, table_name, current_schema, version=2, run_id=run_id)

        return result

    def _save_version(self, source_id: str, table_name: str, schema: TableSchema, version: int, run_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        cols_summary = ", ".join(f"{c.name}:{c.data_type}" for c in schema.columns)
        record = {
            "source_id": source_id,
            "table_name": table_name,
            "version": version,
            "columns_summary": cols_summary,
            "primary_key": ",".join(schema.primary_key),
            "recorded_at": now,
            "run_id": run_id,
        }
        df = pd.DataFrame([record])
        self.writer.write_dataframe(df, self.dataset_id, "pwa_schema_versions", write_disposition="WRITE_APPEND")
