"""Unified cache management and invalidation for Polyglot Warehouse Agent (PWA).

Provides a single entry point to inspect and clear all pipeline caches:
- Semantic Answer Cache (semantic_cache)
- Disk-Persisted Schema Cache (schema_cache)
- In-Memory Semantic Catalog Cache (loader)
- BigQuery Client Singleton (connections)
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any, Dict

from pwa.agent.schema_cache import _CACHE_DIR, invalidate_schema_cache
from pwa.agent.semantic_cache import semantic_cache
from pwa.connections import invalidate_bq_client_cache
from pwa.semantic.loader import invalidate_catalog_cache

logger = logging.getLogger("pwa.cache_manager")

VALID_CACHE_TARGETS = ("all", "semantic", "schema", "catalog", "connections")


def clear_semantic_cache() -> int:
    """Clear the in-memory (and Redis if configured) semantic answer cache."""
    count = len(semantic_cache._entries)
    semantic_cache.clear()
    return count


def clear_schema_cache() -> int:
    """Clear all disk-persisted BQ INFORMATION_SCHEMA JSON cache files."""
    files = list(pathlib.Path(_CACHE_DIR).glob("*.json"))
    count = len(files)
    invalidate_schema_cache()
    return count


def clear_catalog_cache() -> bool:
    """Reset the in-memory parsed SemanticCatalog singleton."""
    invalidate_catalog_cache()
    return True


def clear_connections_cache() -> bool:
    """Reset the process-level BigQuery client singleton."""
    invalidate_bq_client_cache()
    return True


def clear_caches(target: str = "all") -> Dict[str, Any]:
    """Purge specified cache target or all caches by default.

    Args:
        target: One of 'all', 'semantic', 'schema', 'catalog', 'connections'.

    Returns:
        Dict mapping cache names to their invalidation summary details.
    """
    clean_target = (target or "all").lower().strip()
    if clean_target not in VALID_CACHE_TARGETS:
        raise ValueError(f"Invalid cache target '{target}'. Must be one of: {', '.join(VALID_CACHE_TARGETS)}")

    results: Dict[str, Any] = {}

    if clean_target in ("all", "semantic"):
        cnt = clear_semantic_cache()
        results["semantic"] = {"status": "cleared", "entries_removed": cnt}

    if clean_target in ("all", "schema"):
        files_removed = clear_schema_cache()
        results["schema"] = {"status": "cleared", "files_removed": files_removed}

    if clean_target in ("all", "catalog"):
        clear_catalog_cache()
        results["catalog"] = {"status": "cleared"}

    if clean_target in ("all", "connections"):
        clear_connections_cache()
        results["connections"] = {"status": "cleared"}

    logger.info(f"[Cache Manager] Successfully cleared cache target '{clean_target}': {results}")
    return results


clear_all_caches = clear_caches
