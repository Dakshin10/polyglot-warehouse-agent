"""Unit tests for Phase 6 Metrics Telemetry & Semantic Cache Negation Guard."""

from pwa.agent.semantic_cache import SemanticCache
from pwa.metrics import QueryTelemetry, get_metrics_tracker


def test_metrics_tracker_recording():
    tracker = get_metrics_tracker()
    initial_queries = len(tracker.telemetry_history)

    t = QueryTelemetry(
        query_id="q_test_1",
        question="Show total revenue",
        stage_latencies={"router": 0.05, "execution": 0.40},
        prompt_tokens=150,
        completion_tokens=50,
        bytes_scanned=2048,
        cache_hit=False,
        routing_category="ANALYTICAL",
    )
    tracker.record_query(t)

    assert len(tracker.telemetry_history) == initial_queries + 1
    stats = tracker.get_summary_stats()
    assert stats["total_queries"] >= 1


def test_semantic_cache_negation_guard():
    cache = SemanticCache(similarity_threshold=0.85)

    # Enable cache explicitly for test
    cache.put("Show total sales in EU", "EU sales total is $5,000,000")

    # Positive match test
    match_pos = cache.get("Show total sales in EU")
    assert match_pos == "EU sales total is $5,000,000"

    # Negation query should NOT hit cache despite high n-gram overlap
    match_neg = cache.get("Show total sales outside EU")
    assert match_neg is None
