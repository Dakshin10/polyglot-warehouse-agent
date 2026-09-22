"""AdventureWorks 2022 raw ingestion into BigQuery raw_adventureworks.

Source: tituspr/adventureworks2022-excel-format (Kaggle)
Target: BigQuery raw_adventureworks.*

Every raw table receives PWA provenance metadata columns:
  _pwa_ingested_at     TIMESTAMP  — when this row was loaded
  _pwa_run_id          STRING     — pipeline run UUID
  _pwa_source_system   STRING     — "adventureworks"
  _pwa_source_table    STRING     — table name within source
  _pwa_payload_hash    STRING     — SHA-256 of the row payload (for dedup)

Ingestion is idempotent: raw tables are WRITE_TRUNCATE (full snapshot replace).
This is correct because AdventureWorks is a static Kaggle snapshot.
For incremental connectors, WRITE_APPEND with watermark filtering would be used.

The raw layer preserves source semantics — column names and types are kept as
close to the source as possible. No business logic transformations here.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from google.cloud import bigquery

from pwa.connections import get_bq_client
from pwa.settings import get_settings
from pwa.source_registry import get_registry, SourceConfig, SourceTableConfig

logger = logging.getLogger("pwa.adventureworks_ingest")

SOURCE_NAME = "adventureworks"
SOURCE_SYSTEM = "adventureworks"

# PWA metadata columns to add to every raw table
PWA_META_COLS = [
    "_pwa_ingested_at",
    "_pwa_run_id",
    "_pwa_source_system",
    "_pwa_source_table",
    "_pwa_payload_hash",
]


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def discover_source_files(source: SourceConfig) -> dict[str, Path]:
    """Discover actual source files for each registered table.

    Returns: {table_name: Path} for all tables where a file is found.
    """
    import glob

    found: dict[str, Path] = {}
    local_dir = source.local_dir

    if not local_dir.exists():
        logger.warning(f"Source directory does not exist: {local_dir}")
        return found

    for table_cfg in source.tables:
        pattern = str(local_dir / table_cfg.source_file_pattern)
        matches = sorted(glob.glob(pattern))
        if matches:
            # Use the first match (there should be only one per table)
            found[table_cfg.name] = Path(matches[0])
            logger.info(f"  [{table_cfg.name}] → {Path(matches[0]).name}")
        else:
            logger.warning(f"  [{table_cfg.name}] No file matching '{table_cfg.source_file_pattern}'")

    return found


# ---------------------------------------------------------------------------
# Row hash for deduplication
# ---------------------------------------------------------------------------


def _row_hash(row: pd.Series) -> str:
    """Compute a deterministic SHA-256 hash of a row's values."""
    payload = "|".join(str(v) for v in row.values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# DataFrame → BigQuery loader
# ---------------------------------------------------------------------------


def _sanitize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Replace spaces and special characters in column names with underscores."""
    df.columns = [re.sub(r"[^a-zA-Z0-9_]", "_", str(c)).strip("_") for c in df.columns]
    return df


def _add_pwa_metadata(df: pd.DataFrame, run_id: str, table_name: str) -> pd.DataFrame:
    """Add PWA provenance metadata columns to a DataFrame."""
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
    project: str,
    dataset: str,
    table_name: str,
) -> int:
    """Load a DataFrame to BigQuery as a full snapshot (WRITE_TRUNCATE)."""
    table_ref = f"{project}.{dataset}.{table_name}"

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )

    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()

    rows_written = job.output_rows
    logger.info(f"  ✓ Loaded {rows_written:,} rows → `{table_ref}`")
    return rows_written


# ---------------------------------------------------------------------------
# Single-table ingestion
# ---------------------------------------------------------------------------


def ingest_table(
    client: bigquery.Client,
    source: SourceConfig,
    table_cfg: SourceTableConfig,
    file_path: Path,
    run_id: str,
    project: str,
    dataset: str,
) -> dict:
    """Ingest one AdventureWorks table to BigQuery raw layer.

    Returns a result dict with: table_name, status, rows_read, rows_written, error.
    """
    result = {
        "table_name": table_cfg.name,
        "status": "unknown",
        "rows_read": 0,
        "rows_written": 0,
        "file": str(file_path),
        "error": None,
    }

    logger.info(f"Ingesting [{table_cfg.name}] from {file_path.name} ...")

    try:
        # Read file (Excel or CSV)
        suffix = file_path.suffix.lower()
        if suffix in (".xlsx", ".xls"):
            df = pd.read_excel(file_path, dtype=str)
        elif suffix == ".csv":
            df = pd.read_csv(file_path, dtype=str, low_memory=False)
        else:
            result["status"] = "skipped"
            result["error"] = f"Unsupported file type: {suffix}"
            logger.warning(f"  [{table_cfg.name}] Skipped — unsupported format: {suffix}")
            return result

        result["rows_read"] = len(df)
        logger.info(f"  [{table_cfg.name}] Read {len(df):,} rows, {len(df.columns)} columns")

        if df.empty:
            result["status"] = "empty"
            logger.warning(f"  [{table_cfg.name}] Source file is empty.")
            return result

        # Sanitize column names for BigQuery compatibility
        df = _sanitize_column_names(df)

        # Add PWA metadata
        df = _add_pwa_metadata(df, run_id, table_cfg.name)

        # Load to BigQuery
        rows_written = _load_to_bigquery(client, df, project, dataset, table_cfg.name)
        result["rows_written"] = rows_written
        result["status"] = "success"

    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        logger.error(f"  [{table_cfg.name}] FAILED: {exc}")

    return result


# ---------------------------------------------------------------------------
# Full source ingestion
# ---------------------------------------------------------------------------


def ingest_adventureworks(run_id: Optional[str] = None) -> dict:
    """Ingest all AdventureWorks tables to BigQuery raw_adventureworks.

    Returns a summary dict with per-table results.
    """
    import uuid as _uuid

    if run_id is None:
        run_id = str(_uuid.uuid4())

    s = get_settings()
    project = s.gcp_project
    dataset = s.bq_ds_raw_aw
    client = get_bq_client()

    registry = get_registry()
    source = registry.get(SOURCE_NAME)
    if source is None:
        raise ValueError(f"Source '{SOURCE_NAME}' not found in registry. Check config/sources.yaml.")

    logger.info(f"=== ADVENTUREWORKS RAW INGESTION STARTED (run_id={run_id}) ===")
    logger.info(f"Source dir: {source.local_dir}")
    logger.info(f"Target dataset: {project}.{dataset}")

    # Discover files
    logger.info("Discovering source files...")
    file_map = discover_source_files(source)

    if not file_map:
        raise RuntimeError(
            f"No AdventureWorks source files found in {source.local_dir}. Run: pwa ingest download adventureworks"
        )

    results = []
    total_rows_read = 0
    total_rows_written = 0
    failed_tables = []

    for table_cfg in source.tables:
        if table_cfg.name not in file_map:
            logger.warning(f"[{table_cfg.name}] No source file found — skipping.")
            results.append(
                {
                    "table_name": table_cfg.name,
                    "status": "missing_file",
                    "rows_read": 0,
                    "rows_written": 0,
                    "error": f"No file matching '{table_cfg.source_file_pattern}'",
                }
            )
            continue

        result = ingest_table(
            client=client,
            source=source,
            table_cfg=table_cfg,
            file_path=file_map[table_cfg.name],
            run_id=run_id,
            project=project,
            dataset=dataset,
        )
        results.append(result)
        total_rows_read += result.get("rows_read", 0)
        total_rows_written += result.get("rows_written", 0)
        if result["status"] == "failed":
            failed_tables.append(table_cfg.name)

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
    }

    if failed_tables:
        logger.error(f"=== ADVENTUREWORKS INGESTION PARTIAL — FAILED: {failed_tables} ===")
    else:
        logger.info(
            f"=== ADVENTUREWORKS INGESTION COMPLETE — "
            f"{total_rows_written:,} rows written across {len(results)} tables ==="
        )

    return summary


if __name__ == "__main__":
    from pwa.logging_setup import setup_logging

    setup_logging()
    result = ingest_adventureworks()
    raise SystemExit(0 if result["tables_failed"] == 0 else 1)
