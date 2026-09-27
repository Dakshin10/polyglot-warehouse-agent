"""Unit tests for PWA Smart Cache Invalidation engine."""

import pandas as pd

from pwa.agent.semantic_cache import semantic_cache
from pwa.smart_cache import (
    SyncStateStore,
    compute_table_signal,
    evaluate_and_invalidate_cache,
)


def test_compute_table_signal():
    """Verify table signal computation from DataFrame."""
    df = pd.DataFrame(
        [
            {"id": 1, "name": "Alice", "updated_at": "2026-09-16T10:00:00Z"},
            {"id": 2, "name": "Bob", "updated_at": "2026-09-16T11:00:00Z"},
        ]
    )
    signal = compute_table_signal(df, table_name="dim_customer", watermark_col="updated_at", primary_key_cols=["id"])

    assert signal["table_name"] == "dim_customer"
    assert signal["row_count"] == 2
    assert signal["max_watermark"] == "2026-09-16T11:00:00Z"
    assert isinstance(signal["checksum"], str)


def test_smart_invalidation_flow(tmp_path, monkeypatch):
    """Verify smart invalidation flow: initial seed -> no change (preserved) -> change (invalidated)."""
    monkeypatch.setenv("PWA_FORCE_SYNC_CLEAR", "0")

    state_file = tmp_path / "sync_state.json"
    store = SyncStateStore(state_file=state_file)

    df1 = pd.DataFrame([{"id": 1, "val": "A", "updated_at": "2026-09-16T10:00:00Z"}])
    sig1 = compute_table_signal(df1, "test_table", watermark_col="updated_at")
    signals1 = {"test_table": sig1}

    # 1. First run: initial seed (changes detected because no prior state)
    res1 = evaluate_and_invalidate_cache(signals1, state_store=store)
    assert res1["invalidated"] is True
    assert "test_table" in res1["changed_tables"]

    # Populate semantic cache
    semantic_cache.put("What is test_table total?", "Answer is A.")
    assert len(semantic_cache._entries) >= 1

    # 2. Second run with SAME data: no changes detected, cache preserved
    res2 = evaluate_and_invalidate_cache(signals1, state_store=store)
    assert res2["invalidated"] is False
    assert len(res2["changed_tables"]) == 0
    assert len(semantic_cache._entries) >= 1  # Cache preserved!

    # 3. Third run with UPDATED data (watermark advanced + new row)
    df2 = pd.DataFrame(
        [
            {"id": 1, "val": "A", "updated_at": "2026-09-16T10:00:00Z"},
            {"id": 2, "val": "B", "updated_at": "2026-09-16T12:00:00Z"},
        ]
    )
    sig2 = compute_table_signal(df2, "test_table", watermark_col="updated_at")
    signals2 = {"test_table": sig2}

    res3 = evaluate_and_invalidate_cache(signals2, state_store=store)
    assert res3["invalidated"] is True
    assert "test_table" in res3["changed_tables"]
    assert len(semantic_cache._entries) == 0  # Cache purged on real data change!


def test_force_sync_clear_override(tmp_path, monkeypatch):
    """Verify PWA_FORCE_SYNC_CLEAR=1 forces invalidation even without data changes."""
    state_file = tmp_path / "sync_state.json"
    store = SyncStateStore(state_file=state_file)

    df = pd.DataFrame([{"id": 1, "updated_at": "2026-09-16T10:00:00Z"}])
    sig = compute_table_signal(df, "test_table", watermark_col="updated_at")
    signals = {"test_table": sig}

    # Initial seed
    evaluate_and_invalidate_cache(signals, state_store=store)

    # Set force override env var
    monkeypatch.setenv("PWA_FORCE_SYNC_CLEAR", "1")

    res = evaluate_and_invalidate_cache(signals, state_store=store)
    assert res["invalidated"] is True
    assert "test_table" in res["changed_tables"]
