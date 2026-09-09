"""TTL-based schema snapshot cache with disk persistence.

Why disk?
---------
The original in-memory cache was a guaranteed MISS on every fresh CLI
invocation because the Python process restarts each time.  A JSON file
with mtime-based TTL survives process boundaries: the first run after
startup populates it, every subsequent run in the same hour reads the
file at ~0ms, completely skipping the 11-second INFORMATION_SCHEMA
BigQuery round-trip.

Fallback chain
--------------
1. Disk cache hit (< TTL)  →  return immediately  (0 ms)
2. Live BQ INFORMATION_SCHEMA fetch  →  write to disk, return  (~11 s first time only)
3. Any network error          →  return STATIC_MART_SCHEMA  (0 ms, safe approximation)

Public API
----------
get_schema_snapshot(client, project_id, dataset, ttl_seconds) -> dict
    Returns cached snapshot if fresh; fetches & persists otherwise.

invalidate_schema_cache(key=None) -> None
    Removes a disk cache file, or all files if None.
"""

import json
import logging
import os
import pathlib
import time
from typing import Any, Optional

from pwa.agent.bq_tools import schema_snapshot as _fetch_snapshot

logger = logging.getLogger("pwa.agent.schema_cache")

# ---------------------------------------------------------------------------
# Cache directory – sits next to this file so it travels with the project.
# ---------------------------------------------------------------------------
_CACHE_DIR = pathlib.Path(__file__).parent / ".schema_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Default TTL — 1 hour.  Override with env var PWA_SCHEMA_CACHE_TTL_SECONDS.
_DEFAULT_TTL_SECONDS = 3600


def _get_ttl() -> float:
    env_val = os.getenv("PWA_SCHEMA_CACHE_TTL_SECONDS", "").strip()
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    return float(_DEFAULT_TTL_SECONDS)


def _cache_file(project_id: str, dataset: str) -> pathlib.Path:
    safe_key = f"{project_id}.{dataset}".replace("/", "_").replace("\\", "_")
    return _CACHE_DIR / f"{safe_key}.json"


# ---------------------------------------------------------------------------
# Relationship Cardinalities relative to v_movie
# ---------------------------------------------------------------------------
MART_CARDINALITIES: dict[str, str] = {
    "mart.v_movie": "base (1 row per movie)",
    "mart.v_movie_credits": "one-to-one (safe to pre-join, row count stays 1:1)",
    "mart.v_movie_keywords": "one-to-many (JOIN only for keyword filtering; NEVER join before an aggregate like AVG/SUM over movie-level columns, or wrap the join in a pre-aggregation subquery first)",
    "mart.v_movie_full": "pre-joined 1:1 view, safe for direct lookups",
    "mart.v_integrity_exceptions": "monitor (exceptions listing)",
}


def get_view_cardinality(view_name: str) -> str:
    """Return the relationship cardinality description relative to v_movie."""
    clean = view_name.strip().strip("`").lower()
    if not clean.startswith("mart."):
        clean = f"mart.{clean}"
    return MART_CARDINALITIES.get(clean, "unknown")


# ---------------------------------------------------------------------------
# Static schema — used as immediate fallback when live fetch fails.
# Keep in sync with your actual mart views.
# ---------------------------------------------------------------------------
STATIC_MART_SCHEMA: dict[str, list[dict[str, Any]]] = {
    "mart.v_movie": [
        {"name": "movie_id", "type": "INT64", "description": "Primary key"},
        {"name": "title", "type": "STRING", "description": "Movie title"},
        {"name": "budget_usd", "type": "FLOAT64", "description": "Production budget in USD (may be 0 for old films)"},
        {"name": "revenue_usd", "type": "FLOAT64", "description": "Box office revenue in USD"},
        {"name": "profit_usd", "type": "FLOAT64", "description": "Profit in USD (revenue minus budget)"},
        {
            "name": "roi",
            "type": "FLOAT64",
            "description": "Return on Investment ratio (revenue/budget - 1). Unreliable when budget_usd < 1000 — always filter with WHERE budget_usd > 1000 for ROI queries.",
        },
        {"name": "primary_genre", "type": "STRING", "description": "Primary genre"},
        {"name": "release_year", "type": "INT64", "description": "Year of release"},
        {"name": "vote_average", "type": "FLOAT64", "description": "Average TMDB user rating"},
    ],
    "mart.v_movie_credits": [
        {"name": "movie_id", "type": "INT64", "description": "Foreign key to v_movie"},
        {"name": "director_name", "type": "STRING", "description": "Director name"},
        {"name": "lead_actor_name", "type": "STRING", "description": "Lead actor name"},
        {"name": "second_actor_name", "type": "STRING", "description": "Secondary actor"},
        {"name": "cast_size", "type": "INT64", "description": "Total cast members"},
        {"name": "crew_size", "type": "INT64", "description": "Total crew members"},
    ],
    "mart.v_movie_keywords": [
        {"name": "movie_id", "type": "INT64", "description": "Foreign key"},
        {"name": "keyword_id", "type": "INT64", "description": "Keyword ID"},
        {"name": "keyword", "type": "STRING", "description": "Keyword label"},
    ],
    "mart.v_movie_full": [
        {"name": "movie_id", "type": "INT64", "description": "Primary key"},
        {"name": "title", "type": "STRING", "description": "Movie title"},
        {"name": "release_year", "type": "INT64", "description": "Release year"},
        {"name": "revenue_usd", "type": "FLOAT64", "description": "Revenue"},
        {"name": "profit_usd", "type": "FLOAT64", "description": "Profit"},
        {
            "name": "roi",
            "type": "FLOAT64",
            "description": "ROI — filter budget_usd > 1000 to avoid silent-era division-by-zero artifacts",
        },
        {"name": "primary_genre", "type": "STRING", "description": "Primary genre"},
        {"name": "vote_average", "type": "FLOAT64", "description": "Average rating"},
        {"name": "director_name", "type": "STRING", "description": "Director name"},
        {"name": "lead_actor_name", "type": "STRING", "description": "Lead actor"},
    ],
    "mart.v_integrity_exceptions": [
        {"name": "exception_id", "type": "STRING", "description": "Exception ID"},
        {"name": "rule_name", "type": "STRING", "description": "Failed rule"},
        {"name": "severity", "type": "STRING", "description": "Severity"},
    ],
}


def get_schema_snapshot(
    client: Any = None,
    project_id: Optional[str] = None,
    dataset: Optional[str] = None,
    ttl_seconds: Optional[float] = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return a schema snapshot, serving from disk cache if within TTL.

    Disk persistence means every CLI invocation after the first gets a
    cache HIT at ~0ms, eliminating the 11-second INFORMATION_SCHEMA fetch.

    Args:
        client:      BigQuery client (uses get_bq_client() if None).
        project_id:  GCP project (falls back to settings).
        dataset:     BQ dataset name (falls back to settings).
        ttl_seconds: Cache TTL override. Reads PWA_SCHEMA_CACHE_TTL_SECONDS if None.

    Returns:
        Dict mapping ``"dataset.view_name"`` to a list of column descriptors.
    """
    _project = project_id or ""
    _dataset = dataset or ""
    if not _project or not _dataset:
        try:
            from pwa.settings import get_settings

            s = get_settings()
            _project = _project or s.gcp_project
            _dataset = _dataset or s.bq_ds_mart
        except Exception:
            _project = _project or "unknown"
            _dataset = _dataset or "mart"

    ttl = ttl_seconds if ttl_seconds is not None else _get_ttl()
    cache_file = _cache_file(_project, _dataset)

    # 1. Disk cache hit check
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < ttl:
            try:
                snapshot = json.loads(cache_file.read_text(encoding="utf-8"))
                logger.debug(f"[Schema Cache HIT] file='{cache_file.name}' age={age:.0f}s ttl={ttl:.0f}s")
                return snapshot
            except Exception as read_err:
                logger.warning(f"[Schema Cache] Disk read failed ({read_err}) — re-fetching.")
        else:
            logger.debug(f"[Schema Cache EXPIRED] file='{cache_file.name}' age={age:.0f}s ttl={ttl:.0f}s — re-fetching")

    # 2. Live fetch from BigQuery INFORMATION_SCHEMA
    try:
        logger.info(f"[Schema Cache MISS] key='{_project}.{_dataset}' — fetching from BigQuery INFORMATION_SCHEMA")
        snapshot = _fetch_snapshot(client=client, project_id=_project, dataset=_dataset)
        if not snapshot or not any(snapshot.values()):
            logger.warning("[Schema Cache] Live fetch returned empty result — using static fallback.")
            snapshot = STATIC_MART_SCHEMA
        else:
            # Persist to disk for future process invocations
            try:
                cache_file.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
                logger.debug(f"[Schema Cache] Persisted to '{cache_file}'")
            except Exception as write_err:
                logger.warning(f"[Schema Cache] Could not write disk cache ({write_err}) — continuing without.")
    except Exception as err:
        logger.warning(f"[Schema Cache] Live fetch failed ({err}) — using instant static schema fallback.")
        snapshot = STATIC_MART_SCHEMA

    return snapshot


def invalidate_schema_cache(key: Optional[str] = None) -> None:
    """Invalidate the schema disk cache.

    Args:
        key: ``"project.dataset"`` key to remove. Pass None to clear all files.
    """
    if key is None:
        files = list(_CACHE_DIR.glob("*.json"))
        for f in files:
            f.unlink(missing_ok=True)
        logger.info(f"[Schema Cache] Cleared {len(files)} cached file(s) from '{_CACHE_DIR}'.")
    else:
        parts = key.split(".")
        if len(parts) >= 2:
            f = _cache_file(parts[0], parts[1])
        else:
            f = _CACHE_DIR / f"{key}.json"
        if f.exists():
            f.unlink()
            logger.info(f"[Schema Cache] Invalidated '{f}'.")
        else:
            logger.debug(f"[Schema Cache] Key '{key}' not found on disk — nothing to invalidate.")
