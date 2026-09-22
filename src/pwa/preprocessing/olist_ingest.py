"""Olist Brazilian E-Commerce raw ingestion into BigQuery raw_olist.

Source: olistbr/brazilian-ecommerce (Kaggle)
Target: BigQuery raw_olist.*
License: CC BY-NC-SA 4.0 — non-commercial use only.

Preserves the complete Olist relational model:
  - olist_orders
  - olist_customers       (customer_id ≠ customer_unique_id — both preserved)
  - olist_order_items
  - olist_order_payments
  - olist_order_reviews
  - olist_products
  - olist_sellers
  - olist_geolocation
  - olist_product_category_translation

Cross-dataset relationship note:
  seller_id in olist_order_items and olist_sellers
  links to olist_marketing_qualified_leads / olist_closed_deals in raw_olist_marketing.
  This relationship is documented but NOT enforced in the raw layer (source semantics).

Every raw table receives PWA provenance metadata columns.
Ingestion is idempotent (WRITE_TRUNCATE snapshot).
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from google.cloud import bigquery

from pwa.connections import get_bq_client
from pwa.settings import get_settings
from pwa.source_registry import get_registry

logger = logging.getLogger("pwa.olist_ingest")

SOURCE_NAME = "olist"
SOURCE_SYSTEM = "olist"

# Olist-specific: the customer_id / customer_unique_id distinction is critical.
# customer_id is per-order (not stable across orders for the same customer).
# customer_unique_id identifies the physical customer across orders.
# Both must be preserved in the raw table.
CUSTOMER_ID_NOTES = (
    "Olist customer_id identifies the customer associated with a specific order. "
    "It is NOT a stable customer identifier. "
    "Use customer_unique_id to track repeat purchases by the same customer."
)


def _row_hash(row: pd.Series) -> str:
    payload = "|".join(str(v) for v in row.values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sanitize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [re.sub(r"[^a-zA-Z0-9_]", "_", str(c)).strip("_") for c in df.columns]
    return df


def _add_pwa_metadata(df: pd.DataFrame, run_id: str, table_name: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc).isoformat()
    df["_pwa_ingested_at"] = now
    df["_pwa_run_id"] = run_id
    df["_pwa_source_system"] = SOURCE_SYSTEM
    df["_pwa_source_table"] = table_name
    df["_pwa_payload_hash"] = df.apply(_row_hash, axis=1)
    return df


def _load_to_bigquery(
    client: bigquery.Client,
    df: pd.DataFrame,
    table_ref: str,
) -> int:
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()
    logger.info(f"  ✓ Loaded {job.output_rows:,} rows → `{table_ref}`")
    return job.output_rows


def _find_file(local_dir: Path, pattern: str) -> Optional[Path]:
    """Find a single file matching a pattern in local_dir."""
    import glob

    matches = sorted(glob.glob(str(local_dir / pattern)))
    if matches:
        return Path(matches[0])
    # Fallback: try case-insensitive match
    for f in local_dir.iterdir():
        if f.is_file() and pattern.lower().replace("*", "") in f.name.lower():
            return f
    return None


def ingest_olist(run_id: Optional[str] = None) -> dict:
    """Ingest all Olist e-commerce tables to BigQuery raw_olist.

    Preserves the full Olist relational model including the
    customer_id vs customer_unique_id distinction.
    """
    if run_id is None:
        run_id = str(_uuid.uuid4())

    s = get_settings()
    project = s.gcp_project
    dataset = s.bq_ds_raw_olist
    client = get_bq_client()

    registry = get_registry()
    source = registry.get(SOURCE_NAME)
    if source is None:
        raise ValueError(f"Source '{SOURCE_NAME}' not found in registry.")

    logger.info(f"=== OLIST RAW INGESTION STARTED (run_id={run_id}) ===")
    logger.info(f"Source dir: {source.local_dir}")
    logger.info(f"Target dataset: {project}.{dataset}")

    if not source.local_dir.exists():
        raise RuntimeError(f"Olist source directory not found: {source.local_dir}. Run: pwa ingest download olist")

    results = []
    total_rows_read = 0
    total_rows_written = 0
    failed_tables = []

    for table_cfg in source.tables:
        table_name = table_cfg.name
        file_path = _find_file(source.local_dir, table_cfg.source_file_pattern)

        if file_path is None:
            logger.warning(f"[{table_name}] No file matching '{table_cfg.source_file_pattern}' — skipping.")
            results.append({"table_name": table_name, "status": "missing_file", "rows_read": 0, "rows_written": 0})
            continue

        logger.info(f"Ingesting [{table_name}] from {file_path.name} ...")
        result: dict[str, Any] = {
            "table_name": table_name,
            "file": file_path.name,
            "status": "unknown",
            "rows_read": 0,
            "rows_written": 0,
            "error": None,
        }

        try:
            df = pd.read_csv(file_path, dtype=str, low_memory=False)
            result["rows_read"] = len(df)
            logger.info(f"  [{table_name}] Read {len(df):,} rows, {len(df.columns)} columns")

            # Special validation for customers table — both IDs must be present
            if table_name == "olist_customers":
                if "customer_id" not in df.columns or "customer_unique_id" not in df.columns:
                    logger.warning(
                        f"  [{table_name}] WARNING: expected both customer_id and "
                        f"customer_unique_id. Found: {list(df.columns)}"
                    )
                else:
                    n_ids = df["customer_id"].nunique()
                    n_unique = df["customer_unique_id"].nunique()
                    logger.info(
                        f"  [{table_name}] customer_id distinct: {n_ids:,}, "
                        f"customer_unique_id distinct: {n_unique:,} "
                        f"(ratio {n_ids / n_unique:.2f}x — expected > 1.0 for repeat customers)"
                    )

            df = _sanitize_columns(df)
            df = _add_pwa_metadata(df, run_id, table_name)
            table_ref = f"{project}.{dataset}.{table_name}"
            rows_written = _load_to_bigquery(client, df, table_ref)

            result["rows_written"] = rows_written
            result["status"] = "success"
            total_rows_read += result["rows_read"]
            total_rows_written += rows_written

        except Exception as exc:
            result["status"] = "failed"
            result["error"] = str(exc)
            logger.error(f"  [{table_name}] FAILED: {exc}")
            failed_tables.append(table_name)

        results.append(result)

    summary = {
        "source": SOURCE_NAME,
        "run_id": run_id,
        "tables_attempted": len(results),
        "tables_succeeded": sum(1 for r in results if r["status"] == "success"),
        "tables_failed": len(failed_tables),
        "total_rows_read": total_rows_read,
        "total_rows_written": total_rows_written,
        "failed_tables": failed_tables,
        "results": results,
        "note": CUSTOMER_ID_NOTES,
    }

    if failed_tables:
        logger.error(f"=== OLIST INGESTION PARTIAL — FAILED: {failed_tables} ===")
    else:
        logger.info(
            f"=== OLIST INGESTION COMPLETE — {total_rows_written:,} rows written across {len(results)} tables ==="
        )

    return summary


if __name__ == "__main__":
    from pwa.logging_setup import setup_logging

    setup_logging()
    result = ingest_olist()
    raise SystemExit(0 if result["tables_failed"] == 0 else 1)
