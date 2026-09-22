"""Unit tests for PWA cache management module and CLI commands."""

import pathlib

from pwa.agent.schema_cache import _CACHE_DIR
from pwa.agent.semantic_cache import semantic_cache
from pwa.cache_manager import (
    clear_all_caches,
    clear_caches,
    clear_catalog_cache,
    clear_connections_cache,
    clear_schema_cache,
    clear_semantic_cache,
)
from pwa.cli import cmd_clear_cache


def test_clear_semantic_cache():
    """Verify semantic cache clearing."""
    semantic_cache.put("Test question?", "Test answer.")
    assert len(semantic_cache._entries) >= 1

    removed = clear_semantic_cache()
    assert removed >= 1
    assert len(semantic_cache._entries) == 0


def test_clear_schema_cache(tmp_path):
    """Verify disk schema cache clearing."""
    dummy_file = pathlib.Path(_CACHE_DIR) / "test_project.test_dataset.json"
    dummy_file.write_text("{}", encoding="utf-8")
    assert dummy_file.exists()

    removed = clear_schema_cache()
    assert removed >= 1
    assert not dummy_file.exists()


def test_clear_catalog_and_connections_cache():
    """Verify catalog and connections cache invalidation helpers."""
    assert clear_catalog_cache() is True
    assert clear_connections_cache() is True


def test_clear_caches_all():
    """Verify clear_caches with target 'all'."""
    semantic_cache.put("Another test question?", "Another test answer.")

    res = clear_caches(target="all")
    assert "semantic" in res
    assert "schema" in res
    assert "catalog" in res
    assert "connections" in res
    assert res["semantic"]["status"] == "cleared"


def test_cmd_clear_cache_cli():
    """Verify cmd_clear_cache CLI entry point execution."""
    rc = cmd_clear_cache(cache_target="all")
    assert rc == 0
