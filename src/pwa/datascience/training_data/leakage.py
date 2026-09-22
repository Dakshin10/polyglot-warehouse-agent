"""
Temporal Leakage Validator (Phase 2C)
Guarantees that historical feature computation never uses data timestamped after the label event horizon.
"""

import datetime
from typing import Dict, Any, List, Optional
from pwa.agent.errors import PWAError


class TemporalLeakageError(PWAError):
    """Raised when future-dated feature observations leak into training data."""

    pass


class TemporalLeakageValidator:
    def validate_temporal_boundary(
        self,
        feature_timestamp: Any,
        label_timestamp: Any,
        record_id: Optional[str] = None,
    ) -> bool:
        """
        Validates feature_timestamp <= label_timestamp.
        Raises TemporalLeakageError if feature timestamp is strictly in the future relative to label timestamp.
        """
        f_dt = self._to_datetime(feature_timestamp)
        l_dt = self._to_datetime(label_timestamp)

        if f_dt > l_dt:
            raise TemporalLeakageError(
                f"Temporal leakage detected for record {record_id or 'unknown'}: "
                f"feature_timestamp ({f_dt.isoformat()}) > label_timestamp ({l_dt.isoformat()}). "
                "Historical features cannot be computed from future data."
            )
        return True

    def validate_dataset_records(
        self,
        records: List[Dict[str, Any]],
        feature_ts_key: str = "feature_timestamp",
        label_ts_key: str = "label_timestamp",
    ) -> Dict[str, Any]:
        valid_count = 0
        leaked_count = 0

        for r in records:
            f_ts = r.get(feature_ts_key)
            l_ts = r.get(label_ts_key)
            if f_ts and l_ts:
                try:
                    self.validate_temporal_boundary(f_ts, l_ts, str(r.get("entity_id")))
                    valid_count += 1
                except TemporalLeakageError:
                    leaked_count += 1

        return {
            "valid_records": valid_count,
            "leaked_records": leaked_count,
            "clean": leaked_count == 0,
        }

    def _to_datetime(self, ts: Any) -> datetime.datetime:
        if isinstance(ts, datetime.datetime):
            return ts
        if isinstance(ts, datetime.date):
            return datetime.datetime.combine(ts, datetime.time.min)
        if isinstance(ts, str):
            try:
                return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                return datetime.datetime.strptime(ts[:10], "%Y-%m-%d")
        raise ValueError(f"Unsupported timestamp format: {ts}")
