"""Semantic cache for the PWA NL→SQL pipeline.

Avoids redundant LLM and BigQuery calls by serving repeated (or very similar)
questions from an in-process answer cache.

Similarity is computed by character n-gram cosine similarity — no embedding
model or network call is required, making the cache usable even when the LLM
endpoint is unavailable.  If you want richer semantic matching, replace
``_similarity()`` with an embedding-based approach.

Configuration
-------------
PWA_SEMANTIC_CACHE_ENABLED   Set to "1" to enable (default: disabled).
PWA_SEMANTIC_CACHE_TTL       Cache entry TTL in seconds (default: 3600).
PWA_SEMANTIC_CACHE_MAX       Maximum number of cached entries (default: 128).
PWA_SEMANTIC_CACHE_THRESHOLD Minimum cosine similarity to count as a hit (default: 0.92).

Public API
----------
SemanticCache.get(question) -> str | None
SemanticCache.put(question, answer) -> None
SemanticCache.clear() -> None

# Global singleton — import and use directly:
semantic_cache.get(question) / semantic_cache.put(question, answer)
"""

import logging
import math
import os
import time
from collections import Counter
from typing import Optional

logger = logging.getLogger("pwa.agent.semantic_cache")


def _ngrams(text: str, n: int = 3) -> Counter:
    """Return character n-gram frequency Counter for a normalised string."""
    s = text.lower().strip()
    if len(s) < n:
        return Counter({s: 1})
    return Counter(s[i : i + n] for i in range(len(s) - n + 1))


def _cosine_similarity(a: Counter, b: Counter) -> float:
    """Return cosine similarity between two frequency Counters."""
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b[k] for k in a if k in b)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SemanticCache:
    """In-process LRU-ish cache keyed by question semantic similarity."""

    def __init__(
        self,
        max_entries: int = 128,
        ttl_seconds: float = 3600.0,
        similarity_threshold: float = 0.92,
    ) -> None:
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._threshold = similarity_threshold
        # Each entry: {"question": str, "answer": str, "ngrams": Counter, "ts": float}
        self._entries: list[dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, question: str) -> Optional[str]:
        """Look up a cached answer for a semantically similar question.

        Returns the cached answer string, or None on a cache miss.
        """
        if not self._is_enabled():
            return None
        now = time.monotonic()
        q_ngrams = _ngrams(question)
        # Evict expired entries first
        self._evict_expired(now)

        best_sim = 0.0
        best_entry = None
        for entry in self._entries:
            sim = _cosine_similarity(q_ngrams, entry["ngrams"])
            if sim > best_sim:
                best_sim = sim
                best_entry = entry

        if best_entry is not None and best_sim >= self._threshold:
            logger.debug(
                f"[Semantic Cache HIT] similarity={best_sim:.3f} "
                f"(threshold={self._threshold}) for question='{question[:60]}...'"
            )
            return best_entry["answer"]

        logger.debug(f"[Semantic Cache MISS] best_similarity={best_sim:.3f} for question='{question[:60]}...'")
        return None

    def put(self, question: str, answer: str) -> None:
        """Store a question→answer pair in the cache."""
        if not self._is_enabled():
            return
        # Evict oldest if at capacity
        if len(self._entries) >= self._max_entries:
            self._entries.pop(0)
        self._entries.append(
            {
                "question": question,
                "answer": answer,
                "ngrams": _ngrams(question),
                "ts": time.monotonic(),
            }
        )
        logger.debug(f"[Semantic Cache PUT] question='{question[:60]}...' (entries={len(self._entries)})")

    def clear(self) -> None:
        """Clear all cached entries."""
        count = len(self._entries)
        self._entries.clear()
        logger.info(f"[Semantic Cache] Cleared {count} entries.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_enabled(self) -> bool:
        return os.getenv("PWA_SEMANTIC_CACHE_ENABLED", "0").strip() == "1"

    def _evict_expired(self, now: float) -> None:
        ttl = self._get_ttl()
        self._entries = [e for e in self._entries if (now - e["ts"]) < ttl]

    def _get_ttl(self) -> float:
        env_val = os.getenv("PWA_SEMANTIC_CACHE_TTL", "").strip()
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        return self._ttl


# ---------------------------------------------------------------------------
# Global singleton for use by orchestrator
# ---------------------------------------------------------------------------
semantic_cache = SemanticCache(
    max_entries=int(os.getenv("PWA_SEMANTIC_CACHE_MAX", "128")),
    ttl_seconds=float(os.getenv("PWA_SEMANTIC_CACHE_TTL", "3600")),
    similarity_threshold=float(os.getenv("PWA_SEMANTIC_CACHE_THRESHOLD", "0.92")),
)
