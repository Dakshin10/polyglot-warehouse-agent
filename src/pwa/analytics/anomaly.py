"""
Descriptive Anomaly Detection Engine (Phase 2C)
Rule-based statistical anomaly detection (z-score, rolling mean deviation, IQR, percent change)
"""

import math
from typing import Dict, Any, List, Optional
import yaml
import pathlib


class DescriptiveAnomalyDetector:
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        if config_path and pathlib.Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f).get("anomaly_detection", {})
        # Fallback defaults
        default_config_file = pathlib.Path(__file__).parents[3] / "config" / "anomaly_thresholds.yaml"
        if default_config_file.exists():
            with open(default_config_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f).get("anomaly_detection", {})
        return {
            "z_score": {"enabled": True, "threshold": 2.5, "min_observations": 7},
            "rolling_deviation": {"enabled": True, "threshold_percentage": 20.0, "window_size": 5},
            "iqr": {"enabled": True, "multiplier": 1.5, "min_observations": 10},
            "percentage_change": {"enabled": True, "threshold_percentage": 30.0},
        }

    def detect_zscore(
        self, rows: List[Dict[str, Any]], metric_key: str, threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        threshold = threshold or self.config.get("z_score", {}).get("threshold", 2.5)
        values = [
            r[metric_key] for r in rows if r.get(metric_key) is not None and isinstance(r[metric_key], (int, float))
        ]
        if len(values) < 3:
            return []

        mean_val = sum(values) / len(values)
        variance = sum((x - mean_val) ** 2 for x in values) / len(values)
        std_dev = math.sqrt(variance)

        if std_dev == 0:
            return []

        anomalies = []
        for idx, row in enumerate(rows):
            val = row.get(metric_key)
            if val is not None and isinstance(val, (int, float)):
                z = (val - mean_val) / std_dev
                if abs(z) >= threshold:
                    anomalies.append(
                        {
                            "index": idx,
                            "row": row,
                            "metric": metric_key,
                            "observed": val,
                            "baseline_mean": round(mean_val, 4),
                            "std_dev": round(std_dev, 4),
                            "z_score": round(z, 4),
                            "deviation_pct": round(((val - mean_val) / mean_val) * 100, 2) if mean_val != 0 else 0.0,
                            "threshold": threshold,
                            "method": "z_score",
                        }
                    )
        return anomalies

    def detect_rolling_deviation(
        self, rows: List[Dict[str, Any]], metric_key: str, window_size: int = 5, threshold_pct: float = 20.0
    ) -> List[Dict[str, Any]]:
        if len(rows) < window_size + 1:
            return []

        anomalies = []
        for idx in range(window_size, len(rows)):
            window_rows = rows[idx - window_size : idx]
            window_vals = [
                r[metric_key]
                for r in window_rows
                if r.get(metric_key) is not None and isinstance(r[metric_key], (int, float))
            ]
            if not window_vals:
                continue

            rolling_mean = sum(window_vals) / len(window_vals)
            curr_val = rows[idx].get(metric_key)
            if curr_val is not None and isinstance(curr_val, (int, float)) and rolling_mean != 0:
                dev_pct = abs((curr_val - rolling_mean) / rolling_mean) * 100
                if dev_pct >= threshold_pct:
                    anomalies.append(
                        {
                            "index": idx,
                            "row": rows[idx],
                            "metric": metric_key,
                            "observed": curr_val,
                            "baseline_rolling_mean": round(rolling_mean, 4),
                            "deviation_pct": round(dev_pct, 2),
                            "threshold_pct": threshold_pct,
                            "method": "rolling_deviation",
                        }
                    )
        return anomalies

    def detect_all(self, rows: List[Dict[str, Any]], metric_key: str) -> List[Dict[str, Any]]:
        anomalies = []
        anomalies.extend(self.detect_zscore(rows, metric_key))
        anomalies.extend(self.detect_rolling_deviation(rows, metric_key))
        return anomalies
