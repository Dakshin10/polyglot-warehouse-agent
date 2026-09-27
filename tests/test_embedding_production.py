"""Tests for embedding cache (Task 1) and visible fallback logging (Task 2).

Task 1: Entity description embeddings are cached at the schema_agent module
level. The embedding API is called exactly once per entity description across
multiple queries, not once-per-query.

Task 2: get_dense_embedding logs a WARNING (not DEBUG) when no API key is
configured — exactly once per process, not once per call. When key is
configured but both backends fail, logs a WARNING per call.
get_embedding_status() returns a queryable status string.
"""

import logging
import os
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Task 1 — Entity description embedding cache
# ---------------------------------------------------------------------------

class TestEntityDescriptionEmbeddingCache:

    def setup_method(self):
        """Clear the module-level entity desc cache before each test."""
        from pwa.agent.pipeline import schema_agent
        schema_agent._ENTITY_DESC_EMBEDDING_CACHE.clear()

    def test_entity_desc_embeddings_computed_once_across_two_queries(self):
        """Entity description embeddings are fetched from API only on the FIRST
        query that reaches the dense path; subsequent queries use the cache.

        Call counts (2 identical zero-overlap queries):
          First query : 1 (question) + N (entity descriptions) = N+1 calls
          Second query: 1 (question) + 0 (all cached)           =   1 call
          Total                                                  = N+2 calls
        Not: 2*(N+1) = 2N+2 calls (which is what would happen without the cache).
        """
        from pwa.agent.pipeline import schema_agent
        from pwa.agent.pipeline.schema_agent import GroundingAgent

        question = "how much stuff do we have sitting around"
        desc_texts = set(schema_agent._CATALOG_SEMANTIC_DESCRIPTIONS.values())
        n_entities = len(schema_agent._CATALOG_SEMANTIC_DESCRIPTIONS)

        call_log: list[str] = []

        def tracking_embedding(text: str):
            call_log.append(text)
            return [0.1, 0.2, 0.3, 0.4]  # non-None so dense path executes

        with patch("pwa.agent.models.get_dense_embedding", side_effect=tracking_embedding):
            agent = GroundingAgent()
            agent.ground_question(question)  # first query: fills cache
            agent.ground_question(question)  # second query: cache hits

        desc_calls = [t for t in call_log if t in desc_texts]
        question_calls = [t for t in call_log if t not in desc_texts]

        assert len(desc_calls) == n_entities, (
            f"Entity desc embeddings should be computed exactly {n_entities} times "
            f"(first query only), not {len(desc_calls)}. Cache not working."
        )
        assert len(question_calls) == 2, (
            f"Question embeddings should be computed fresh each query (2 total), "
            f"got {len(question_calls)}."
        )
        total = len(call_log)
        without_cache = 2 * (n_entities + 1)
        with_cache = n_entities + 2
        assert total == with_cache, (
            f"Total calls: expected {with_cache} (with cache), "
            f"got {total} (without cache would be {without_cache})."
        )

    def test_cache_invalidated_on_description_change(self):
        """A changed description text produces a different cache key and is
        re-fetched — stale vectors are never returned for edited descriptions."""
        from pwa.agent.pipeline.schema_agent import _get_cached_entity_embedding
        from pwa.agent.pipeline import schema_agent

        call_count = [0]

        def counting_embedding(text: str) -> list[float]:
            call_count[0] += 1
            return [float(call_count[0])] * 4  # distinct vector per call

        with patch("pwa.agent.models.get_dense_embedding", side_effect=counting_embedding):
            v1 = _get_cached_entity_embedding("fact_inventory", "original description")
            v2 = _get_cached_entity_embedding("fact_inventory", "original description")  # cache hit
            v3 = _get_cached_entity_embedding("fact_inventory", "edited description")    # new key

        assert v1 == v2, "Same description should return cached vector"
        assert v1 != v3, "Different description should produce a new cache entry"
        assert call_count[0] == 2, (
            f"Expected 2 API calls (original + edited), got {call_count[0]}"
        )

    def test_heuristic_path_bypasses_embedding_entirely(self):
        """Questions that match _DOMAIN_HEURISTICS short-circuit before the
        dense embedding path — confirming embedding cost is zero for common queries."""
        from pwa.agent.pipeline.schema_agent import GroundingAgent

        keyword_questions = [
            "show me total revenue",
            "list all inventory items",
            "which customers placed orders",
            "show purchase orders from suppliers",
            "closed deals this month",
            "marketing leads by origin",
        ]

        embedding_call_count = [0]

        def counting_embedding(text: str) -> list[float]:
            embedding_call_count[0] += 1
            return [0.1, 0.2, 0.3, 0.4]

        with patch("pwa.agent.models.get_dense_embedding", side_effect=counting_embedding):
            agent = GroundingAgent()
            for q in keyword_questions:
                agent.ground_question(q)

        assert embedding_call_count[0] == 0, (
            f"Heuristic-matched questions must NOT trigger embedding API calls. "
            f"Got {embedding_call_count[0]} calls for {len(keyword_questions)} keyword queries."
        )


# ---------------------------------------------------------------------------
# Task 2 — Visible fallback logging and get_embedding_status()
# ---------------------------------------------------------------------------

class TestEmbeddingFallbackVisibility:

    def setup_method(self):
        """Reset module-level embedding state before each test."""
        import pwa.agent.models as m
        m._NO_KEY_WARNED = False
        m._EMBEDDING_STATUS = "unknown"

    def teardown_method(self):
        """Restore module-level embedding state after each test."""
        import pwa.agent.models as m
        m._NO_KEY_WARNED = False
        m._EMBEDDING_STATUS = "unknown"

    def test_no_key_warning_fires_exactly_once_not_per_call(self, caplog):
        """When no API key is set, a WARNING is logged exactly once across
        multiple calls — not once per call."""
        import pwa.agent.models as m

        no_key_env = {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": "", "GROQ_API_KEY": ""}

        with patch.dict(os.environ, no_key_env):
            with caplog.at_level(logging.WARNING, logger="pwa.agent.models"):
                m.get_dense_embedding("first call")
                m.get_dense_embedding("second call")
                m.get_dense_embedding("third call")

        warning_records = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "API key" in r.message
        ]
        assert len(warning_records) == 1, (
            f"Expected exactly 1 WARNING for missing key, got {len(warning_records)}: "
            f"{[r.message for r in warning_records]}"
        )
        assert "TF-IDF" in warning_records[0].message, (
            "WARNING should mention the TF-IDF fallback so operators understand the degradation."
        )

    def test_no_key_status_is_no_key(self):
        """get_embedding_status() returns 'no_key' when keys are absent."""
        import pwa.agent.models as m

        no_key_env = {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": "", "GROQ_API_KEY": ""}
        with patch.dict(os.environ, no_key_env):
            m.get_dense_embedding("any text")

        assert m.get_embedding_status() == "no_key"

    def test_api_error_logged_at_warning_level(self, caplog):
        """When key is configured but both backends raise exceptions, a WARNING
        is logged (not DEBUG) so operators see the degradation in normal logs."""
        import pwa.agent.models as m

        key_env = {"GEMINI_API_KEY": "fake-key-present"}

        with patch.dict(os.environ, key_env):
            with patch("litellm.embedding", side_effect=RuntimeError("litellm down")):
                with patch("google.genai.Client") as mock_client:
                    mock_client.return_value.models.embed_content.side_effect = (
                        RuntimeError("genai down")
                    )
                    with caplog.at_level(logging.WARNING, logger="pwa.agent.models"):
                        result = m.get_dense_embedding("test text")

        assert result is None
        warning_records = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "backends failed" in r.message
        ]
        assert len(warning_records) == 1, (
            f"Expected 1 WARNING for api_error, got {len(warning_records)}"
        )
        assert m.get_embedding_status() == "api_error"

    def test_status_available_on_success(self):
        """get_embedding_status() returns 'available' when a real embedding succeeds."""
        import pwa.agent.models as m

        fake_response = MagicMock()
        fake_response.data = [{"embedding": [0.1, 0.2, 0.3]}]

        key_env = {"GEMINI_API_KEY": "fake-key"}
        with patch.dict(os.environ, key_env):
            with patch("litellm.embedding", return_value=fake_response):
                result = m.get_dense_embedding("test")

        assert result == [0.1, 0.2, 0.3]
        assert m.get_embedding_status() == "available"

    def test_status_unknown_before_first_call(self):
        """get_embedding_status() returns 'unknown' before any embedding call is made."""
        import pwa.agent.models as m

        # setup_method already reset _EMBEDDING_STATUS to "unknown"
        assert m.get_embedding_status() == "unknown"

    def test_get_embedding_status_function_exists_and_is_importable(self):
        """get_embedding_status is a named public function, importable for health checks."""
        from pwa.agent.models import get_embedding_status
        status = get_embedding_status()
        assert status in ("unknown", "no_key", "available", "api_error"), (
            f"Unexpected status value: {status!r}"
        )
