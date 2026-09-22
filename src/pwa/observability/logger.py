"""Structured JSON operational logger for PWA enterprise ingestion engine."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


class StructuredLogger:
    """Formats telemetry logs as structured JSON strings without exposing sensitive credentials."""

    def __init__(self, name: str) -> None:
        self.logger = logging.getLogger(name)

    def log_event(
        self,
        event_type: str,
        run_id: str,
        source_id: str,
        table_name: str | None = None,
        status: str = "INFO",
        records_read: int = 0,
        records_written: int = 0,
        duration_seconds: float = 0.0,
        error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "run_id": run_id,
            "source_id": source_id,
            "table_name": table_name,
            "status": status,
            "records_read": records_read,
            "records_written": records_written,
            "duration_seconds": round(duration_seconds, 4),
            "error": error,
        }
        if extra:
            log_payload["extra"] = extra

        msg = json.dumps(log_payload)
        if status in ("ERROR", "FAIL", "CRITICAL"):
            self.logger.error(msg)
        elif status in ("WARN", "WARNING"):
            self.logger.warning(msg)
        else:
            self.logger.info(msg)
