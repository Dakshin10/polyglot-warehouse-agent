"""Staging transformation processor for PWA warehouse foundation.

Standardizes raw tables into staging tables:
- snake_case column names
- explicit BigQuery data types
- deterministic deduplication
- source metadata preservation
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
import pandas as pd

from pwa.settings import get_settings
from pwa.warehouse.bigquery.writer import BigQueryWriter

logger = logging.getLogger("pwa.warehouse.staging")


def to_snake_case(name: str) -> str:
    """Convert PascalCase / camelCase / spaced column names to snake_case."""
    # Preserved metadata column names
    if name.startswith("_pwa_"):
        return name
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1)
    s3 = re.sub(r"[^a-zA-Z0-9_]", "_", s2).lower()
    return re.sub(r"_+", "_", s3).strip("_")


class StagingProcessor:
    """Processor that reads raw data, applies deterministic staging transformations, and writes to staging."""

    def __init__(self, writer: Optional[BigQueryWriter] = None) -> None:
        settings = get_settings()
        self.writer = writer or BigQueryWriter()
        self.ds_enterprise = settings.bq_ds_staging_ent
        self.ds_marketplace = settings.bq_ds_staging_mkt

        self.writer.create_dataset_if_not_exists(self.ds_enterprise)
        self.writer.create_dataset_if_not_exists(self.ds_marketplace)

    def process_table(
        self,
        raw_df: pd.DataFrame,
        source_system: str,
        table_name: str,
        primary_key: Optional[str | list[str]] = None,
        target_domain: str = "enterprise",
    ) -> dict[str, Any]:
        """Transform raw DataFrame into normalized staging table."""
        if raw_df.empty:
            return {"status": "skipped", "table_name": table_name, "rows_written": 0}

        df = raw_df.copy()

        # 1. Column name standardization (snake_case)
        df.columns = [to_snake_case(c) for c in df.columns]

        # 2. Null normalization (empty string / spaces -> None)
        for col in df.columns:
            if not col.startswith("_pwa_"):
                df[col] = df[col].apply(
                    lambda v: None if pd.isnull(v) or str(v).strip() in ("", "nan", "None", "null") else v
                )

        # 3. Deterministic deduplication
        pk_cols = []
        if primary_key:
            pk_list = [primary_key] if isinstance(primary_key, str) else primary_key
            pk_cols = [to_snake_case(k) for k in pk_list if to_snake_case(k) in df.columns]

        if pk_cols:
            before_len = len(df)
            df = df.drop_duplicates(subset=pk_cols, keep="first")
            dupes_removed = before_len - len(df)
            if dupes_removed > 0:
                logger.info(
                    f"[{source_system}.{table_name}] Deduplicated: removed {dupes_removed} duplicate row(s) on {pk_cols}"
                )

        target_ds = self.ds_marketplace if target_domain == "marketplace" else self.ds_enterprise
        staging_table_name = f"stg_{source_system}_{table_name}"

        res = self.writer.write_dataframe(
            df=df,
            dataset_id=target_ds,
            table_id=staging_table_name,
            write_disposition="WRITE_TRUNCATE",
        )

        res["staging_table"] = f"{target_ds}.{staging_table_name}"
        return res
