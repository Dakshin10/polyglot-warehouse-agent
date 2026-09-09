"""Unit tests for TTL-based schema cache (Task P1-3).

Tests verify: cache hit within TTL, expiry forces re-fetch, manual invalidation,
global clear, and that BQ is not called on a cache hit.

All BigQuery interactions are mocked — no cloud credentials needed.
"""

import time
from unittest.mock import patch

import pytest

from pwa.agent import schema_cache as sc


@pytest.fixture(autouse=True)
def clear_cache():
    """Ensure a clean cache state before each test."""
    sc.invalidate_schema_cache()
    yield
    sc.invalidate_schema_cache()


def _make_mock_snapshot():
    return {
        "mart.v_movie": [{"name": "movie_id", "type": "INTEGER", "description": "ID"}],
        "mart.v_movie_credits": [],
    }


class TestCacheHit:
    def test_second_call_within_ttl_does_not_hit_bq(self):
        """Within TTL, the second call must return cached data and NOT call BQ."""
        mock_snapshot = _make_mock_snapshot()
        with patch("pwa.agent.schema_cache._fetch_snapshot", return_value=mock_snapshot) as mock_fetch:
            # First call — populates cache
            result1 = sc.get_schema_snapshot(ttl_seconds=300)
            # Second call — must be served from cache
            result2 = sc.get_schema_snapshot(ttl_seconds=300)

            assert mock_fetch.call_count == 1, "BQ should only be called once within TTL"
            assert result1 == result2

    def test_cache_returns_same_snapshot(self):
        """Cached snapshot must equal the original BQ response (disk round-trip makes `is` identity impossible)."""
        mock_snapshot = _make_mock_snapshot()
        with patch("pwa.agent.schema_cache._fetch_snapshot", return_value=mock_snapshot):
            r1 = sc.get_schema_snapshot(ttl_seconds=300)
            r2 = sc.get_schema_snapshot(ttl_seconds=300)
            assert r1 == r2, "Cache should return equal data"


class TestCacheExpiry:
    def test_call_after_ttl_expiry_refetches_from_bq(self):
        """After TTL expires, a new BQ call must be made."""
        mock_snapshot = _make_mock_snapshot()
        with patch("pwa.agent.schema_cache._fetch_snapshot", return_value=mock_snapshot) as mock_fetch:
            # Use a very short TTL
            sc.get_schema_snapshot(ttl_seconds=0.05)
            time.sleep(0.1)
            sc.get_schema_snapshot(ttl_seconds=0.05)

            assert mock_fetch.call_count == 2, "BQ should be called again after TTL expires"

    def test_zero_ttl_always_refetches(self):
        """TTL=0 should always bypass cache."""
        mock_snapshot = _make_mock_snapshot()
        with patch("pwa.agent.schema_cache._fetch_snapshot", return_value=mock_snapshot) as mock_fetch:
            sc.get_schema_snapshot(ttl_seconds=0)
            sc.get_schema_snapshot(ttl_seconds=0)
            assert mock_fetch.call_count == 2


class TestManualInvalidation:
    def test_invalidate_specific_key_forces_refetch(self, tmp_path, monkeypatch):
        """Manual invalidation of a specific key should force a re-fetch."""
        monkeypatch.setattr(sc, "_CACHE_DIR", tmp_path)
        mock_snapshot = _make_mock_snapshot()
        with patch("pwa.agent.schema_cache._fetch_snapshot", return_value=mock_snapshot) as mock_fetch:
            with patch("pwa.agent.schema_cache._get_ttl", return_value=300.0):
                sc.get_schema_snapshot()  # populates cache — project/dataset resolved at runtime
                cache_files = list(tmp_path.glob("*.json"))
                assert len(cache_files) == 1, "One cache file should exist after first call"
                key_stem = cache_files[0].stem  # e.g. "salitsteel-502008.mart"
                sc.invalidate_schema_cache(key=key_stem)
                assert not cache_files[0].exists(), "Cache file should be removed after invalidation"
                sc.get_schema_snapshot()  # should re-fetch
                assert mock_fetch.call_count == 2

    def test_invalidate_none_clears_all(self, tmp_path, monkeypatch):
        """invalidate_schema_cache(None) should clear all cache files."""
        monkeypatch.setattr(sc, "_CACHE_DIR", tmp_path)
        mock_snapshot = _make_mock_snapshot()
        with patch("pwa.agent.schema_cache._fetch_snapshot", return_value=mock_snapshot) as mock_fetch:
            sc.get_schema_snapshot(project_id="proj1", dataset="mart", ttl_seconds=300)
            sc.get_schema_snapshot(project_id="proj2", dataset="ds2", ttl_seconds=300)
            assert mock_fetch.call_count == 2

            sc.invalidate_schema_cache()  # clear all
            assert len(list(tmp_path.glob("*.json"))) == 0, "All cache files should be cleared"

            sc.get_schema_snapshot(project_id="proj1", dataset="mart", ttl_seconds=300)
            assert mock_fetch.call_count == 3

    def test_invalidate_nonexistent_key_does_not_raise(self):
        """Invalidating a key that doesn't exist should be a no-op."""
        sc.invalidate_schema_cache(key="no-such-project.no-such-dataset")  # Should not raise


class TestEnvTTL:
    def test_env_var_ttl_is_respected(self, monkeypatch):
        """PWA_SCHEMA_CACHE_TTL_SECONDS env var should set the default TTL."""
        monkeypatch.setenv("PWA_SCHEMA_CACHE_TTL_SECONDS", "0.05")
        mock_snapshot = _make_mock_snapshot()
        with patch("pwa.agent.schema_cache._fetch_snapshot", return_value=mock_snapshot) as mock_fetch:
            sc.get_schema_snapshot()  # first call
            time.sleep(0.1)
            sc.get_schema_snapshot()  # should re-fetch after 0.05s TTL
            assert mock_fetch.call_count == 2


class TestCardinalityAnnotations:
    def test_cardinality_mappings_exist(self):
        """All mart views must have explicit cardinality annotations."""
        expected_views = [
            "mart.v_movie",
            "mart.v_movie_credits",
            "mart.v_movie_keywords",
            "mart.v_movie_full",
            "mart.v_integrity_exceptions",
        ]
        for v in expected_views:
            assert v in sc.MART_CARDINALITIES
            assert sc.get_view_cardinality(v) != "unknown"

    def test_keywords_cardinality_is_one_to_many(self):
        card = sc.get_view_cardinality("mart.v_movie_keywords")
        assert "one-to-many" in card
