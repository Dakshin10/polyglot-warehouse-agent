"""Dataset freshness and SLA monitoring module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import pandas as pd


class FreshnessStatus(str, Enum):
    FRESH = "FRESH"
    WARNING = "WARNING"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


@dataclass
class FreshnessResult:
    """Represents a dataset freshness evaluation result."""

    source_id: str
    table_name: str
    last_ingested_at: Optional[str]
    delay_minutes: float
    sla_max_delay_minutes: int
    status: FreshnessStatus
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FreshnessTracker:
    """Monitors dataset freshness against configured SLA thresholds."""

    def evaluate_freshness(
        self,
        source_id: str,
        table_name: str,
        last_ingested_at: Optional[str],
        sla_max_delay_minutes: int = 1440,
    ) -> FreshnessResult:
        if not last_ingested_at:
            return FreshnessResult(
                source_id=source_id,
                table_name=table_name,
                last_ingested_at=None,
                delay_minutes=-1.0,
                sla_max_delay_minutes=sla_max_delay_minutes,
                status=FreshnessStatus.UNKNOWN,
            )

        try:
            last_dt = pd.to_datetime(last_ingested_at, utc=True)
            now_dt = datetime.now(timezone.utc)
            delay_minutes = (now_dt - last_dt).total_seconds() / 60.0

            if delay_minutes <= sla_max_delay_minutes:
                status = FreshnessStatus.FRESH
            elif delay_minutes <= (sla_max_delay_minutes * 1.5):
                status = FreshnessStatus.WARNING
            else:
                status = FreshnessStatus.STALE

            return FreshnessResult(
                source_id=source_id,
                table_name=table_name,
                last_ingested_at=last_ingested_at,
                delay_minutes=round(delay_minutes, 2),
                sla_max_delay_minutes=sla_max_delay_minutes,
                status=status,
            )
        except Exception:
            return FreshnessResult(
                source_id=source_id,
                table_name=table_name,
                last_ingested_at=last_ingested_at,
                delay_minutes=-1.0,
                sla_max_delay_minutes=sla_max_delay_minutes,
                status=FreshnessStatus.UNKNOWN,
            )
