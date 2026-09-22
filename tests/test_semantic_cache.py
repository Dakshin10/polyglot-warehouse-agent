"""Unit tests for the semantic cache (Task P2-3).

All tests set PWA_SEMANTIC_CACHE_ENABLED=1 via monkeypatch so the cache is
active during the test, then restore the env state afterwards.
"""

import time

import pytest

from pwa.agent.semantic_cache import SemanticCache, _ngrams, _cosine_similarity


@pytest.fixture
def cache():
    """Return a fresh enabled SemanticCache for each test."""
    c = SemanticCache(max_entries=10, ttl_seconds=300.0, similarity_threshold=0.92)
    return c


@pytest.fixture(autouse=True)
def enable_cache(monkeypatch):
    monkeypatch.setenv("PWA_SEMANTIC_CACHE_ENABLED", "1")


class TestNgramSimilarity:
    def test_identical_strings_have_similarity_one(self):
        a = _ngrams("which movie had the highest revenue?")
        b = _ngrams("which movie had the highest revenue?")
        assert _cosine_similarity(a, b) == pytest.approx(1.0)

    def test_completely_different_strings_low_similarity(self):
        a = _ngrams("apple")
        b = _ngrams("zzzzz")
        assert _cosine_similarity(a, b) < 0.1

    def test_similar_paraphrase_high_similarity(self):
        a = _ngrams("which movie had the highest revenue?")
        b = _ngrams("which film had the highest revenue?")
        sim = _cosine_similarity(a, b)
        assert sim > 0.7, f"Expected high similarity, got {sim}"


class TestCacheHit:
    def test_exact_repeat_returns_cached_answer(self, cache):
        cache.put("which movie had the highest revenue?", "Avatar had the highest revenue.")
        result = cache.get("which movie had the highest revenue?")
        assert result == "Avatar had the highest revenue."

    def test_near_paraphrase_returns_cached_answer(self):
        """A very similar question should also hit the cache at a lower threshold."""
        # Use a cache with threshold 0.90 — measured similarity for this paraphrase is ~0.914
        low_threshold_cache = SemanticCache(max_entries=10, ttl_seconds=300.0, similarity_threshold=0.90)
        q1 = "which movie had the highest revenue"
        q2 = "which movie has the highest revenue"  # 'had' vs 'has'
        low_threshold_cache.put(q1, "Avatar.")
        result = low_threshold_cache.get(q2)
        assert result == "Avatar.", "Expected cache hit for near-paraphrase but got miss"

    def test_cache_miss_for_different_question(self, cache):
        cache.put("which movie had the highest revenue?", "Avatar.")
        result = cache.get("who directed Inception?")
        assert result is None

    def test_cache_miss_when_disabled(self, monkeypatch, cache):
        monkeypatch.setenv("PWA_SEMANTIC_CACHE_ENABLED", "0")
        cache.put("which movie had the highest revenue?", "Avatar.")
        result = cache.get("which movie had the highest revenue?")
        assert result is None, "Cache should be bypassed when disabled"

    def test_put_does_nothing_when_disabled(self, monkeypatch, cache):
        monkeypatch.setenv("PWA_SEMANTIC_CACHE_ENABLED", "0")
        cache.put("some question", "some answer")
        assert len(cache._entries) == 0


class TestCacheExpiry:
    def test_entry_after_ttl_is_a_miss(self, cache):
        """Expired entries must not be returned."""
        cache._ttl = 0.05  # 50ms TTL
        cache.put("which movie had the highest revenue?", "Avatar.")
        time.sleep(0.1)
        result = cache.get("which movie had the highest revenue?")
        assert result is None

    def test_entry_within_ttl_is_a_hit(self, cache):
        cache.put("which movie had the highest revenue?", "Avatar.")
        result = cache.get("which movie had the highest revenue?")
        assert result is not None


class TestCacheCapacity:
    def test_oldest_entry_evicted_at_max_capacity(self):
        cache = SemanticCache(max_entries=3, ttl_seconds=300, similarity_threshold=0.99)
        cache.put("q1 aaaaaa", "a1")
        cache.put("q2 bbbbbb", "a2")
        cache.put("q3 cccccc", "a3")
        cache.put("q4 dddddd", "a4")  # Should evict q1
        assert len(cache._entries) == 3
        assert all(e["question"] != "q1 aaaaaa" for e in cache._entries)


class TestCacheClear:
    def test_clear_removes_all_entries(self, cache):
        cache.put("q1", "a1")
        cache.put("q2", "a2")
        cache.clear()
        assert len(cache._entries) == 0
        assert cache.get("q1") is None


class TestRedisBacking:
    """PWA_REDIS_URL unset (the default) must never touch redis at all."""

    def test_no_redis_url_never_imports_redis(self, cache, monkeypatch):
        monkeypatch.delenv("PWA_REDIS_URL", raising=False)
        cache.put("q1", "a1")
        assert cache.get("q1") == "a1"
        assert cache._redis is None

    def test_put_writes_through_to_redis(self, monkeypatch):
        import sys
        import types

        mock_redis_module = types.ModuleType("redis")
        mock_client = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        mock_redis_module.from_url = lambda *a, **k: mock_client  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "redis", mock_redis_module)
        monkeypatch.setenv("PWA_REDIS_URL", "redis://localhost:6379/0")

        cache = SemanticCache(max_entries=10, ttl_seconds=300.0, similarity_threshold=0.92)
        mock_client.hvals.return_value = []
        cache.put("what is total revenue", "42")

        mock_client.hset.assert_called_once()
        args = mock_client.hset.call_args
        assert args[0][0] == "pwa:semantic_cache"
        mock_client.expire.assert_called_once()

    def test_get_syncs_entries_written_by_another_replica(self, monkeypatch):
        import json
        import sys
        import types

        mock_redis_module = types.ModuleType("redis")
        mock_client = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        mock_redis_module.from_url = lambda *a, **k: mock_client  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "redis", mock_redis_module)
        monkeypatch.setenv("PWA_REDIS_URL", "redis://localhost:6379/0")

        cache = SemanticCache(max_entries=10, ttl_seconds=300.0, similarity_threshold=0.92)
        remote_entry = json.dumps({"question": "what is total revenue", "answer": "42", "ts": time.time()})
        mock_client.hvals.return_value = [remote_entry]

        # Never written locally, but should be visible via the Redis sync in get().
        assert cache.get("what is total revenue") == "42"

    def test_falls_back_gracefully_when_redis_connection_fails(self, monkeypatch):
        import sys
        import types

        mock_redis_module = types.ModuleType("redis")

        def _boom(*a, **k):
            raise ConnectionError("no route to host")

        mock_redis_module.from_url = _boom  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "redis", mock_redis_module)
        monkeypatch.setenv("PWA_REDIS_URL", "redis://unreachable:6379/0")

        cache = SemanticCache(max_entries=10, ttl_seconds=300.0, similarity_threshold=0.92)
        cache.put("q1", "a1")  # must not raise
        assert cache.get("q1") == "a1"  # local-only fallback still works
