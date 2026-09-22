"""Change Data Capture (CDC) abstractions and event model for PWA ingestion engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import pandas as pd


class CdcOperation(str, Enum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    READ = "READ"


@dataclass
class CdcChangeEvent:
    """Represents a standardized Change Data Capture event."""

    source_system: str
    source_table: str
    operation: CdcOperation
    primary_key: dict[str, Any]
    after_payload: Optional[dict[str, Any]] = None
    before_payload: Optional[dict[str, Any]] = None
    source_timestamp: Optional[str] = None
    ingestion_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_id: Optional[str] = None


class CdcAdapter:
    """Adapter interface for parsing raw change streams into structured CDC events."""

    def __init__(self, source_name: str) -> None:
        self.source_name = source_name

    def parse_change_log(
        self,
        df: pd.DataFrame,
        primary_key_cols: list[str],
        op_col: str = "_pwa_op",
        previous_snapshot: Optional[pd.DataFrame] = None,
    ) -> list[CdcChangeEvent]:
        """Convert a pandas DataFrame containing raw change log records into CdcChangeEvent objects.

        Args:
            previous_snapshot: Optional prior-state DataFrame (same primary key columns)
                used to populate `before_payload` on UPDATE/DELETE events. Without it,
                there is no prior state to diff against and `before_payload` stays None
                (this adapter has no transaction log to read, so it can only recover
                "before" values when the caller supplies the last known snapshot).
        """
        events: list[CdcChangeEvent] = []
        if df.empty:
            return events

        previous_by_pk: dict[tuple, dict[str, Any]] = {}
        if previous_snapshot is not None and not previous_snapshot.empty:
            for _, prev_row in previous_snapshot.iterrows():
                prev_dict = prev_row.to_dict()
                key = tuple(prev_dict.get(col) for col in primary_key_cols)
                previous_by_pk[key] = prev_dict

        for _, row in df.iterrows():
            row_dict = row.to_dict()
            op_str = str(row_dict.get(op_col, "INSERT")).upper()
            try:
                op = CdcOperation(op_str)
            except ValueError:
                op = CdcOperation.INSERT

            pk = {col: row_dict.get(col) for col in primary_key_cols if col in row_dict}

            before_payload = None
            if op in (CdcOperation.UPDATE, CdcOperation.DELETE):
                key = tuple(row_dict.get(col) for col in primary_key_cols)
                before_payload = previous_by_pk.get(key)

            events.append(
                CdcChangeEvent(
                    source_system=self.source_name,
                    source_table=str(row_dict.get("_pwa_source_table", "unknown")),
                    operation=op,
                    primary_key=pk,
                    after_payload=row_dict if op != CdcOperation.DELETE else None,
                    before_payload=before_payload,
                    source_timestamp=str(row_dict.get("_pwa_extracted_at", datetime.now(timezone.utc).isoformat())),
                )
            )

        return events
