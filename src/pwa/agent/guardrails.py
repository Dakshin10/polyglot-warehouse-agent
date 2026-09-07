"""Security & execution guardrails for PWA NLP query pipeline."""

import logging
import os
import re
import time

from google.cloud import bigquery

from pwa.connections import get_bq_client

logger = logging.getLogger("pwa.agent.guardrails")

# Default thresholds
DEFAULT_MAX_BYTES_SCANNED = 100_000_000  # 100 MB
DEFAULT_MAX_QUERIES_PER_MIN = 10

# Prompt injection signatures
PROMPT_INJECTION_PATTERNS = [
    r"\bignore\s+(?:previous|all|prior|above)\s+(?:instructions|prompts|rules)\b",
    r"\bdisregard\s+(?:previous|all|prior|above)\b",
    r"\bsystem\s+prompt\b",
    r"\boverride\s+(?:system|instructions|security)\b",
    r"\brun\s+this\s+sql\s+instead\b",
    r"\bexecute\s+(?:the\s+following|this)\s+sql\b",
    r"\byou\s+are\s+now\b",
    r"\bbypass\s+security\b",
]


def check_prompt_injection(question: str) -> None:
    """Pre-check question text for prompt injection signatures before starting pipeline.

    Raises:
        ValueError: If prompt injection pattern is detected.
    """
    if not question:
        return

    q_lower = question.lower()
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            logger.warning(f"[Security Guardrail] Prompt injection attempt detected in question: '{question}'")
            raise ValueError("Security Violation: Prompt injection attempt detected. Question refused.")


class RateLimiter:
    """In-process sliding window rate limiter."""

    def __init__(self, max_queries_per_min: int | None = None) -> None:
        self._timestamps: list[float] = []
        self._custom_max = max_queries_per_min

    @property
    def max_queries_per_min(self) -> int:
        if self._custom_max is not None:
            return self._custom_max
        env_val = os.getenv("PWA_AGENT_MAX_QUERIES_PER_MIN", "").strip()
        if env_val:
            try:
                return int(env_val)
            except ValueError:
                pass
        return DEFAULT_MAX_QUERIES_PER_MIN

    def check_rate_limit(self) -> None:
        """Enforce rate limit check.

        Raises:
            ValueError: If rate limit threshold is exceeded.
        """
        now = time.time()
        window_start = now - 60.0
        # Evict timestamps older than 60 seconds
        self._timestamps = [ts for ts in self._timestamps if ts >= window_start]

        limit = self.max_queries_per_min
        if len(self._timestamps) >= limit:
            logger.warning(
                f"[Rate Limit Exceeded] Executed {len(self._timestamps)} queries in past 60s (limit={limit})."
            )
            raise ValueError(
                "Rate Limit Exceeded: Too many query requests. Please wait before asking another question."
            )

        self._timestamps.append(now)

    def reset(self) -> None:
        """Reset rate limiter state for testing."""
        self._timestamps.clear()


# Global rate limiter instance
rate_limiter = RateLimiter()


def dry_run_check_bytes(sql: str, max_bytes: int | None = None) -> int:
    """Perform a BigQuery dry-run to check estimated bytes scanned against safety limit.

    Args:
        sql: SQL query to evaluate.
        max_bytes: Maximum allowed bytes scanned (defaults to PWA_AGENT_MAX_BYTES_SCANNED or 100MB).

    Returns:
        Estimated bytes scanned.

    Raises:
        ValueError: If estimated bytes scanned exceeds max_bytes threshold.
    """
    if max_bytes is None:
        env_bytes = os.getenv("PWA_AGENT_MAX_BYTES_SCANNED", "").strip()
        if env_bytes:
            try:
                max_bytes = int(env_bytes)
            except ValueError:
                max_bytes = DEFAULT_MAX_BYTES_SCANNED
        else:
            max_bytes = DEFAULT_MAX_BYTES_SCANNED

    client = get_bq_client()
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    query_job = client.query(sql, job_config=job_config)
    estimated_bytes = query_job.total_bytes_processed or 0

    logger.debug(f"[Dry Run Guard] Estimated bytes scanned: {estimated_bytes} (limit: {max_bytes})")

    if estimated_bytes > max_bytes:
        logger.warning(
            f"[Cost Guard Exceeded] Query estimated to scan {estimated_bytes} bytes, exceeding limit of {max_bytes} bytes."
        )
        raise ValueError(
            f"Query too broad: Estimated bytes scanned ({estimated_bytes} bytes) exceeds safety limit ({max_bytes} bytes). "
            "Please narrow your question."
        )

    return estimated_bytes
