"""Deterministic payload hashing utilities for PWA data provenance."""

from __future__ import annotations

import hashlib
from typing import Any
import pandas as pd

# Volatile metadata headers to exclude from payload hash calculation
VOLATILE_META_COLS = {
    "_pwa_ingested_at",
    "_pwa_run_id",
    "_pwa_source_system",
    "_pwa_source_table",
    "_pwa_batch_id",
    "_pwa_extracted_at",
    "_pwa_record_hash",
    "_pwa_payload_hash",
}


def compute_payload_hash(row: pd.Series | dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash of a record's data payload.

    Excludes volatile metadata headers so payload hash depends strictly
    on source business values.
    """
    if isinstance(row, pd.Series):
        items = sorted((str(k), str(v)) for k, v in row.items() if str(k) not in VOLATILE_META_COLS and pd.notnull(v))
    elif isinstance(row, dict):
        items = sorted((str(k), str(v)) for k, v in row.items() if str(k) not in VOLATILE_META_COLS and v is not None)
    else:
        raise TypeError(f"Unsupported row type for payload hashing: {type(row)}")

    payload_str = "|".join(f"{k}:{v}" for k, v in items)
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


def add_provenance_metadata(
    df: pd.DataFrame,
    run_id: str,
    source_system: str,
    source_table: str,
    batch_id: int = 0,
) -> pd.DataFrame:
    """Add standardized PWA provenance metadata columns to a DataFrame."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

    df["_pwa_ingested_at"] = now
    df["_pwa_run_id"] = run_id
    df["_pwa_source_system"] = source_system
    df["_pwa_source_table"] = source_table
    df["_pwa_batch_id"] = batch_id
    df["_pwa_extracted_at"] = now

    # Compute payload hash per row
    df["_pwa_payload_hash"] = df.apply(compute_payload_hash, axis=1)
    df["_pwa_record_hash"] = df["_pwa_payload_hash"]

    return df
