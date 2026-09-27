"""Structured Observability Metrics Tracker (S-03)

Tracks stage execution latencies (p50/p95/p99 histograms), LLM prompt/completion token usage,
BigQuery bytes scanned, and cache hit/miss counters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict

logger = logging.getLogger("pwa.metrics")


@dataclass
class StageMetric:
    stage_name: str
    duration_seconds: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class QueryTelemetry:
    query_id: str
    question: str
    stage_latencies: Dict[str, float] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    bytes_scanned: int = 0
    cache_hit: bool = False
    routing_category: str = "UNKNOWN"
    exec_status: str = "SUCCESS"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MetricsTracker:
    """Central singleton telemetry collector emitting structured metrics logs."""

    _instance: MetricsTracker | None = None
    telemetry_history: list[QueryTelemetry]
    cache_hits: int
    cache_misses: int

    def __new__(cls) -> MetricsTracker:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.telemetry_history = []
            cls._instance.cache_hits = 0
            cls._instance.cache_misses = 0
        return cls._instance

    def record_query(self, telemetry: QueryTelemetry) -> None:
        """Record completed query telemetry."""
        if telemetry.cache_hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

        self.telemetry_history.append(telemetry)

        total_tokens = telemetry.prompt_tokens + telemetry.completion_tokens
        total_latency = sum(telemetry.stage_latencies.values())

        logger.info(
            f"[METRICS] query_id={telemetry.query_id} category={telemetry.routing_category} "
            f"cache_hit={telemetry.cache_hit} latency_sec={total_latency:.3f} "
            f"bytes_scanned={telemetry.bytes_scanned} tokens={total_tokens} "
            f"latencies={telemetry.stage_latencies}"
        )

    def get_summary_stats(self) -> Dict[str, Any]:
        """Return aggregated summary metrics."""
        total_queries = len(self.telemetry_history)
        hit_ratio = (
            self.cache_hits / (self.cache_hits + self.cache_misses)
            if (self.cache_hits + self.cache_misses) > 0
            else 0.0
        )
        return {
            "total_queries": total_queries,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_ratio": round(hit_ratio, 4),
        }


def get_metrics_tracker() -> MetricsTracker:
    return MetricsTracker()
