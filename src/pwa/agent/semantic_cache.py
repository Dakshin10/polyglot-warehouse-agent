"""Semantic cache for the PWA NL→SQL pipeline.

Avoids redundant LLM and BigQuery calls by serving repeated (or very similar)
questions from an answer cache.

Similarity is computed by character n-gram cosine similarity — no embedding
model or network call is required, making the cache usable even when the LLM
endpoint is unavailable.  If you want richer semantic matching, replace
``_similarity()`` with an embedding-based approach.

Storage backend
----------------
By default the cache is in-process only, which means every replica behind a
load balancer has its own cache with its own hit rate, and a restart empties
it. Set PWA_REDIS_URL to back it with Redis instead: every `put()` writes the
entry to a shared Redis hash (and reads sync the recent window from there
before running the same n-gram similarity search locally), so hit rate no
longer depends on which replica served a given request. Falls back to
in-process-only if `redis` isn't installed or the connection fails — a cache
should never be a hard dependency for answering a question.

Configuration
-------------
PWA_SEMANTIC_CACHE_ENABLED   Set to "1" to enable (default: disabled).
PWA_SEMANTIC_CACHE_TTL       Cache entry TTL in seconds (default: 3600).
PWA_SEMANTIC_CACHE_MAX       Maximum number of cached entries (default: 128).
PWA_SEMANTIC_CACHE_THRESHOLD Minimum cosine similarity to count as a hit (default: 0.92).
PWA_REDIS_URL                redis://host:port/db URL. When set, backs the
                              cache with a shared Redis hash (see above).

Public API
----------
SemanticCache.get(question) -> str | None
SemanticCache.put(question, answer) -> None
SemanticCache.clear() -> None

# Global singleton — import and use directly:
semantic_cache.get(question) / semantic_cache.put(question, answer)
"""

import json
import logging
import math
import os
import re
import time
from collections import Counter
from typing import Any, Optional

logger = logging.getLogger("pwa.agent.semantic_cache")

_REDIS_KEY = "pwa:semantic_cache"


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


_NEGATION_TERMS = re.compile(
    r"\b(not|outside|except|excluding|without|other than|non|neither|nor)\b", re.IGNORECASE
)


def _has_negation_mismatch(q1: str, q2: str) -> bool:
    """Return True if one question contains negation/exclusion terms that the other lacks."""
    neg1 = set(_NEGATION_TERMS.findall(q1.lower()))
    neg2 = set(_NEGATION_TERMS.findall(q2.lower()))
    return neg1 != neg2


class SemanticCache:
    """Cache keyed by question semantic similarity, in-process by default,
    optionally synced through a shared Redis hash (see module docstring)."""

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
        self._redis: Any = None
        self._redis_checked = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, question: str) -> Optional[str]:
        """Look up a cached answer for a semantically similar question.

        Returns the cached answer string, or None on a cache miss.
        """
        if not self._is_enabled():
            return None
        self._sync_from_redis()
        now = time.time()
        q_ngrams = _ngrams(question)
        # Evict expired entries first
        self._evict_expired(now)

        best_sim = 0.0
        best_entry = None
        for entry in self._entries:
            if _has_negation_mismatch(question, entry["question"]):
                continue  # Guard against false positive matches on negated/exclusion queries

            sim = _cosine_similarity(q_ngrams, entry["ngrams"])
            if sim > best_sim:
                best_sim = sim
                best_entry = entry

        if best_entry is not None and best_sim >= self._threshold:
            logger.info(
                f"[Semantic Cache HIT] similarity={best_sim:.3f} (threshold={self._threshold}) "
                f"question='{question}' matched cached_question='{best_entry['question']}'"
            )
            return best_entry["answer"]

        logger.debug(f"[Semantic Cache MISS] best_similarity={best_sim:.3f} for question='{question[:60]}...'")
        return None

    def put(self, question: str, answer: str) -> None:
        """Store a question→answer pair in the cache."""
        if not self._is_enabled():
            return
        entry: dict[str, Any] = {
            "question": question,
            "answer": answer,
            "ngrams": _ngrams(question),
            "ts": time.time(),
        }
        # Evict oldest if at capacity
        if len(self._entries) >= self._max_entries:
            self._entries.pop(0)
        self._entries.append(entry)
        logger.debug(f"[Semantic Cache PUT] question='{question[:60]}...' (entries={len(self._entries)})")
        self._write_to_redis(question, answer, entry["ts"])

    def clear(self) -> None:
        """Clear all cached entries (local process only — does not clear Redis,
        since other replicas may still be legitimately serving from it)."""
        count = len(self._entries)
        self._entries.clear()
        logger.info(f"[Semantic Cache] Cleared {count} entries.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_enabled(self) -> bool:
        return os.getenv("PWA_SEMANTIC_CACHE_ENABLED", "1").strip() == "1"

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

    # ------------------------------------------------------------------
    # Redis backing (optional — every method here fails open to "no Redis")
    # ------------------------------------------------------------------

    def _get_redis_client(self) -> Any:
        """Lazily construct (once) and cache a Redis client, or None if unavailable."""
        if self._redis_checked:
            return self._redis
        self._redis_checked = True

        redis_url = os.getenv("PWA_REDIS_URL", "").strip()
        if not redis_url:
            return None
        try:
            import redis

            client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
            client.ping()
            self._redis = client
            logger.info("[Semantic Cache] Connected to Redis backing store.")
        except ImportError:
            logger.warning(
                "PWA_REDIS_URL is set but the 'redis' package is not installed "
                "(pip install polyglot-warehouse-agent[cache]) — falling back to in-process-only cache."
            )
        except Exception as exc:
            logger.warning(
                f"[Semantic Cache] Could not connect to Redis ({exc}); falling back to in-process-only cache."
            )
        return self._redis

    def _sync_from_redis(self) -> None:
        """Pull the shared entry window from Redis into the local working set
        before running similarity search, so a hit written by another replica
        is visible here too."""
        client = self._get_redis_client()
        if client is None:
            return
        try:
            raw_entries = client.hvals(_REDIS_KEY)
            by_question = {e["question"]: e for e in self._entries}
            for raw in raw_entries:
                try:
                    record = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                q = record.get("question")
                if not q or q in by_question:
                    continue
                by_question[q] = {
                    "question": q,
                    "answer": record.get("answer", ""),
                    "ngrams": _ngrams(q),
                    "ts": record.get("ts", time.time()),
                }
            self._entries = sorted(by_question.values(), key=lambda e: e["ts"])[-self._max_entries :]
        except Exception as exc:
            logger.warning(f"[Semantic Cache] Redis sync failed ({exc}); continuing with local entries only.")

    def _write_to_redis(self, question: str, answer: str, ts: float) -> None:
        client = self._get_redis_client()
        if client is None:
            return
        try:
            field = str(abs(hash(question)))
            client.hset(_REDIS_KEY, field, json.dumps({"question": question, "answer": answer, "ts": ts}))
            client.expire(_REDIS_KEY, int(self._get_ttl()))
        except Exception as exc:
            logger.warning(f"[Semantic Cache] Redis write failed ({exc}); entry kept locally only.")


# ---------------------------------------------------------------------------
# Global singleton for use by orchestrator
# ---------------------------------------------------------------------------
semantic_cache = SemanticCache(
    max_entries=int(os.getenv("PWA_SEMANTIC_CACHE_MAX", "128")),
    ttl_seconds=float(os.getenv("PWA_SEMANTIC_CACHE_TTL", "3600")),
    similarity_threshold=float(os.getenv("PWA_SEMANTIC_CACHE_THRESHOLD", "0.92")),
)
