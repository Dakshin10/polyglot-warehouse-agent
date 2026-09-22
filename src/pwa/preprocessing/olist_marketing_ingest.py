"""Olist Marketing Funnel raw ingestion into BigQuery raw_olist_marketing.

Source: olistbr/marketing-funnel-olist (Kaggle)
Target: BigQuery raw_olist_marketing.*
License: CC BY-NC-SA 4.0 — non-commercial use only.

Tables:
  - olist_marketing_qualified_leads  — MQL records with lead source and timing
  - olist_closed_deals               — closed deals linking MQLs to sellers

Critical cross-dataset relationship:
  olist_closed_deals.seller_id → raw_olist.olist_sellers.seller_id

This is the join that connects the marketing funnel to marketplace orders:
  marketing_lead → seller → marketplace_order → order_item → product

This relationship is validated in quality gates but NOT enforced in raw layer.

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

logger = logging.getLogger("pwa.olist_marketing_ingest")

SOURCE_NAME = "olist_marketing"
SOURCE_SYSTEM = "olist_marketing"

# Key cross-dataset relationship documentation
CROSS_DATASET_NOTE = (
    "olist_closed_deals.seller_id is a foreign key to raw_olist.olist_sellers.seller_id. "
    "This cross-dataset join links the marketing funnel (lead → seller) "
    "to marketplace activity (seller → order_item → product). "
    "Validate this relationship in quality gates before creating curated views."
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


def _load_to_bigquery(client: bigquery.Client, df: pd.DataFrame, table_ref: str) -> int:
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()
    logger.info(f"  ✓ Loaded {job.output_rows:,} rows → `{table_ref}`")
    return job.output_rows


def _find_file(local_dir: Path, pattern: str) -> Optional[Path]:
    import glob

    matches = sorted(glob.glob(str(local_dir / pattern)))
    if matches:
        return Path(matches[0])
    for f in local_dir.iterdir():
        if f.is_file() and pattern.lower().replace("*", "").replace(".csv", "") in f.name.lower():
            return f
    return None


def validate_cross_dataset_relationship(run_id: str) -> dict:
    """Validate that seller_ids in closed_deals exist in olist_sellers.

    This is the critical cross-dataset join between marketing and marketplace.
    Returns a validation result dict.
    """
    s = get_settings()
    client = get_bq_client()
    project = s.gcp_project

    sql = f"""
    SELECT
      COUNT(DISTINCT cd.seller_id) AS total_sellers_in_deals,
      COUNT(DISTINCT CASE WHEN os.seller_id IS NOT NULL THEN cd.seller_id END) AS matched_sellers,
      COUNT(DISTINCT CASE WHEN os.seller_id IS NULL THEN cd.seller_id END) AS orphan_sellers
    FROM `{project}.{s.bq_ds_raw_marketing}.olist_closed_deals` cd
    LEFT JOIN `{project}.{s.bq_ds_raw_olist}.olist_sellers` os
      USING (seller_id)
    WHERE cd.seller_id IS NOT NULL
    """

    try:
        rows = list(client.query(sql).result())
        row = rows[0]
        orphans = int(row["orphan_sellers"])
        total = int(row["total_sellers_in_deals"])
        matched = int(row["matched_sellers"])

        result = {
            "total_sellers_in_deals": total,
            "matched_sellers": matched,
            "orphan_sellers": orphans,
            "match_rate": matched / total if total > 0 else 0.0,
            "passed": orphans == 0,
        }

        if orphans == 0:
            logger.info(
                f"Cross-dataset validation PASSED: all {total} seller_ids in closed_deals exist in olist_sellers."
            )
        else:
            logger.warning(
                f"Cross-dataset validation: {orphans}/{total} seller_ids in "
                f"closed_deals have NO matching record in olist_sellers. "
                f"This may indicate data quality issues."
            )

        return result

    except Exception as exc:
        logger.warning(f"Could not validate cross-dataset relationship: {exc}")
        return {"passed": None, "error": str(exc)}


def ingest_olist_marketing(run_id: Optional[str] = None) -> dict:
    """Ingest Olist Marketing Funnel tables to BigQuery raw_olist_marketing."""
    if run_id is None:
        run_id = str(_uuid.uuid4())

    s = get_settings()
    project = s.gcp_project
    dataset = s.bq_ds_raw_marketing
    client = get_bq_client()

    registry = get_registry()
    source = registry.get(SOURCE_NAME)
    if source is None:
        raise ValueError(f"Source '{SOURCE_NAME}' not found in registry.")

    logger.info(f"=== OLIST MARKETING INGESTION STARTED (run_id={run_id}) ===")
    logger.info(f"Source dir: {source.local_dir}")
    logger.info(f"Target dataset: {project}.{dataset}")
    logger.info(f"Cross-dataset note: {CROSS_DATASET_NOTE}")

    if not source.local_dir.exists():
        raise RuntimeError(
            f"Olist Marketing source directory not found: {source.local_dir}. Run: pwa ingest download olist_marketing"
        )

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

            # Log seller_id presence for cross-dataset validation
            if "seller_id" in df.columns:
                n_with_seller = df["seller_id"].notna().sum()
                logger.info(
                    f"  [{table_name}] seller_id present: {n_with_seller:,}/{len(df):,} rows "
                    f"(links to raw_olist.olist_sellers)"
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

    # Validate cross-dataset relationship (runs after both olist and olist_marketing loaded)
    cross_validation = {}
    if not failed_tables:
        try:
            logger.info("Validating cross-dataset relationship (seller_id)...")
            cross_validation = validate_cross_dataset_relationship(run_id)
        except Exception as exc:
            logger.warning(f"Cross-dataset validation skipped: {exc}")
            cross_validation = {"skipped": True}

    summary = {
        "source": SOURCE_NAME,
        "run_id": run_id,
        "tables_attempted": len(results),
        "tables_succeeded": sum(1 for r in results if r["status"] == "success"),
        "tables_failed": len(failed_tables),
        "total_rows_read": total_rows_read,
        "total_rows_written": total_rows_written,
        "failed_tables": failed_tables,
        "cross_dataset_validation": cross_validation,
        "results": results,
    }

    if failed_tables:
        logger.error(f"=== OLIST MARKETING INGESTION PARTIAL — FAILED: {failed_tables} ===")
    else:
        logger.info(
            f"=== OLIST MARKETING INGESTION COMPLETE — "
            f"{total_rows_written:,} rows written across {len(results)} tables ==="
        )

    return summary


if __name__ == "__main__":
    from pwa.logging_setup import setup_logging

    setup_logging()
    result = ingest_olist_marketing()
    raise SystemExit(0 if result["tables_failed"] == 0 else 1)
