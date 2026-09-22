"""Smart Cache Invalidation Engine for Polyglot Warehouse Agent (PWA).

Monitors source table state (watermarks, row counts, and checksums) on each sync run
and invalidates pipeline caches ONLY when underlying data has actually changed or when
PWA_FORCE_SYNC_CLEAR=1 is set as a manual override.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from pwa.cache_manager import clear_caches

logger = logging.getLogger("pwa.smart_cache")

_STATE_FILE = pathlib.Path(__file__).parent / ".sync_state.json"


class SyncStateStore:
    """Persistence manager for tracking source table watermarks and checksums."""

    def __init__(self, state_file: pathlib.Path | None = None) -> None:
        self.state_file = pathlib.Path(state_file) if state_file else _STATE_FILE

    def load_state(self) -> Dict[str, Dict[str, Any]]:
        """Load stored table sync signals from disk."""
        if not self.state_file.exists():
            return {}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception as exc:
            logger.warning(f"[SyncStateStore] Failed to load sync state ({exc}); using empty state.")
            return {}

    def save_state(self, state: Dict[str, Dict[str, Any]]) -> None:
        """Save table sync signals to disk."""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            logger.debug(f"[SyncStateStore] Saved state for {len(state)} table(s) to '{self.state_file}'.")
        except Exception as exc:
            logger.warning(f"[SyncStateStore] Failed to save sync state ({exc}).")

    def update_signals(self, new_signals: Dict[str, Dict[str, Any]]) -> None:
        """Merge and persist updated signals into stored state."""
        state = self.load_state()
        state.update(new_signals)
        self.save_state(state)


def compute_table_signal(
    df: pd.DataFrame,
    table_name: str,
    watermark_col: Optional[str] = None,
    primary_key_cols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compute a lightweight change detection signal dictionary for a DataFrame.

    Signal fields:
        table_name: str
        row_count: int
        max_watermark: Optional[str]
        checksum: str (md5 hash of row count + key column summary)
    """
    row_count = len(df)
    max_watermark = None

    if watermark_col and watermark_col in df.columns and not df.empty:
        try:
            max_val = df[watermark_col].max()
            max_watermark = str(max_val) if pd.notna(max_val) else None
        except Exception:
            max_watermark = None

    # Compute lightweight checksum
    hasher = hashlib.md5()
    hasher.update(f"{table_name}:{row_count}".encode("utf-8"))

    if not df.empty:
        # Use primary key columns or first 2 columns to calculate sample checksum
        cols_to_hash = primary_key_cols if primary_key_cols else list(df.columns[:2])
        valid_cols = [c for c in cols_to_hash if c in df.columns]
        if valid_cols:
            sample_str = str(df[valid_cols].head(10).to_dict(orient="records"))
            hasher.update(sample_str.encode("utf-8"))

    checksum = hasher.hexdigest()

    return {
        "table_name": table_name,
        "row_count": row_count,
        "watermark_col": watermark_col,
        "max_watermark": max_watermark,
        "checksum": checksum,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def detect_table_changes(
    current_signals: Dict[str, Dict[str, Any]],
    state_store: Optional[SyncStateStore] = None,
) -> Tuple[bool, List[str], Dict[str, str]]:
    """Compare current table signals against stored state.

    Returns:
        (has_changed: bool, list_of_changed_tables: list[str], reasons: dict[str, str])
    """
    store = state_store or SyncStateStore()
    stored_state = store.load_state()

    force_flag = os.getenv("PWA_FORCE_SYNC_CLEAR", "0").strip() == "1"
    if force_flag:
        tables = list(current_signals.keys())
        reasons = {t: "PWA_FORCE_SYNC_CLEAR env var set to 1" for t in tables}
        return True, tables, reasons

    changed_tables: List[str] = []
    reasons: Dict[str, str] = {}

    for table_name, curr in current_signals.items():
        prev = stored_state.get(table_name)
        if prev is None:
            changed_tables.append(table_name)
            reasons[table_name] = "Initial seed (no prior state stored)"
            continue

        # 1. Check watermark advancement
        curr_wm = curr.get("max_watermark")
        prev_wm = prev.get("max_watermark")
        if curr_wm is not None and prev_wm is not None and curr_wm != prev_wm:
            changed_tables.append(table_name)
            reasons[table_name] = f"Watermark advanced ({prev_wm} -> {curr_wm})"
            continue

        # 2. Check row count change
        curr_cnt = curr.get("row_count", 0)
        prev_cnt = prev.get("row_count", 0)
        if curr_cnt != prev_cnt:
            changed_tables.append(table_name)
            reasons[table_name] = f"Row count changed ({prev_cnt} -> {curr_cnt})"
            continue

        # 3. Check checksum
        curr_chk = curr.get("checksum")
        prev_chk = prev.get("checksum")
        if curr_chk and prev_chk and curr_chk != prev_chk:
            changed_tables.append(table_name)
            reasons[table_name] = "Data checksum changed"
            continue

    has_changed = len(changed_tables) > 0
    return has_changed, changed_tables, reasons


def evaluate_and_invalidate_cache(
    current_signals: Dict[str, Dict[str, Any]],
    force: bool = False,
    cache_target: str = "all",
    state_store: Optional[SyncStateStore] = None,
) -> Dict[str, Any]:
    """Evaluate change signals and invalidate pipeline caches ONLY if data has changed.

    Args:
        current_signals: Table signals calculated during sync run.
        force: If True, forces cache invalidation regardless of signals.
        cache_target: Cache target to purge ('all', 'semantic', 'schema', etc.).
        state_store: Custom SyncStateStore instance if provided.

    Returns:
        Summary dict containing invalidation status and cache purge results.
    """
    store = state_store or SyncStateStore()
    has_changed, changed_tables, reasons = detect_table_changes(current_signals, state_store=store)

    should_clear = has_changed or force or (os.getenv("PWA_FORCE_SYNC_CLEAR", "0").strip() == "1")

    if should_clear:
        logger.info(
            f"[Smart Cache Invalidation] Data change detected in {len(changed_tables)} table(s): "
            f"{changed_tables}. Triggering cache purge (target='{cache_target}')."
        )
        for tbl in changed_tables:
            logger.info(f"  - Table '{tbl}': {reasons.get(tbl, 'Changed')}")

        purge_result = clear_caches(target=cache_target)
        store.update_signals(current_signals)

        return {
            "invalidated": True,
            "changed_tables": changed_tables,
            "reasons": reasons,
            "purge_result": purge_result,
        }

    logger.info(
        f"[Smart Cache Invalidation] Sync run — no changes detected across {len(current_signals)} table(s). "
        "Preserving pipeline caches."
    )
    return {
        "invalidated": False,
        "changed_tables": [],
        "reasons": {},
        "purge_result": {},
    }
