"""BigQuery warehouse writer abstraction.

Centralizes BigQuery dataset creation, table management, batch loading,
snapshot vs. append writing, retry policies, and offline mock support for unit tests.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import pandas as pd

from pwa.settings import get_settings

logger = logging.getLogger("pwa.warehouse.bigquery.writer")


class BigQueryWriter:
    """Polymorphic writer abstraction for BigQuery warehouse operations.

    Supports offline mock mode when GCP credentials are missing, enabling
    100% deterministic unit testing without requiring live GCP access.
    """

    def __init__(self, project: Optional[str] = None, mock: bool = False) -> None:
        from pwa.settings import ProductionEnvironmentError

        settings = get_settings()
        self.project = project or settings.gcp_project
        self.mock = mock
        self._client = None
        self._mock_tables: dict[str, pd.DataFrame] = {}

        if not self.mock:
            try:
                from pwa.connections import get_bq_client

                self._client = get_bq_client()
            except Exception as exc:
                if settings.is_production:
                    raise ProductionEnvironmentError(
                        f"Production mode error: BigQuery client initialization failed ({exc}). "
                        "Mock mode is forbidden in production."
                    ) from exc
                logger.info(f"BigQuery client initialization fallback to mock mode ({exc}).")
                self.mock = True
        elif settings.is_production:
            raise ProductionEnvironmentError(
                "Production mode error: Explicit mock mode requested for BigQueryWriter, "
                "which is forbidden in production."
            )

    def create_dataset_if_not_exists(self, dataset_id: str, location: str = "EU") -> bool:
        """Ensure a BigQuery dataset exists."""
        if self.mock:
            logger.info(f"[MOCK BQ] Created dataset: {self.project}.{dataset_id}")
            return True

        from google.cloud import bigquery
        from google.cloud.exceptions import NotFound

        assert self._client is not None, "BigQueryWriter is not mocked but has no live client"
        dataset_ref = f"{self.project}.{dataset_id}"
        try:
            self._client.get_dataset(dataset_ref)
            return True
        except NotFound:
            ds = bigquery.Dataset(dataset_ref)
            ds.location = location
            self._client.create_dataset(ds, exists_ok=True)
            logger.info(f"Created BigQuery dataset: `{dataset_ref}` in {location}")
            return True

    def write_dataframe(
        self,
        df: pd.DataFrame,
        dataset_id: str,
        table_id: str,
        write_disposition: str = "WRITE_TRUNCATE",
    ) -> dict[str, Any]:
        """Write a pandas DataFrame to a BigQuery table with specified disposition."""
        table_ref = f"{self.project}.{dataset_id}.{table_id}"

        if self.mock or self._client is None:
            if write_disposition == "WRITE_TRUNCATE" or table_ref not in self._mock_tables:
                self._mock_tables[table_ref] = df.copy()
            else:
                self._mock_tables[table_ref] = pd.concat([self._mock_tables[table_ref], df], ignore_index=True)

            logger.info(f"[MOCK BQ] Wrote {len(df)} rows to `{table_ref}` ({write_disposition})")
            return {
                "status": "success",
                "table_ref": table_ref,
                "rows_written": len(df),
                "write_disposition": write_disposition,
                "mock": True,
            }

        from google.cloud import bigquery

        job_config = bigquery.LoadJobConfig(
            write_disposition=getattr(bigquery.WriteDisposition, write_disposition),
            autodetect=True,
        )

        job = self._client.load_table_from_dataframe(df, table_ref, job_config=job_config)
        job.result()

        logger.info(f"✓ Loaded {job.output_rows:,} rows -> `{table_ref}` ({write_disposition})")
        return {
            "status": "success",
            "table_ref": table_ref,
            "rows_written": job.output_rows,
            "write_disposition": write_disposition,
            "mock": False,
        }

    def get_table_dataframe(self, dataset_id: str, table_id: str) -> pd.DataFrame:
        """Fetch contents of a BigQuery table as a DataFrame."""
        table_ref = f"{self.project}.{dataset_id}.{table_id}"

        if self.mock or self._client is None:
            return self._mock_tables.get(table_ref, pd.DataFrame())

        query = f"SELECT * FROM `{table_ref}`"
        return self._client.query(query).to_dataframe()

    def get_row_count(self, dataset_id: str, table_id: str) -> int:
        """Get row count for a table."""
        table_ref = f"{self.project}.{dataset_id}.{table_id}"

        if self.mock or self._client is None:
            df = self._mock_tables.get(table_ref)
            return len(df) if df is not None else 0

        query = f"SELECT COUNT(*) AS cnt FROM `{table_ref}`"
        df = self._client.query(query).to_dataframe()
        return int(df["cnt"].iloc[0])

    def merge_dataframe(
        self,
        df: pd.DataFrame,
        dataset_id: str,
        table_id: str,
        primary_keys: list[str],
    ) -> dict[str, Any]:
        """Perform a MERGE / UPSERT operation on a target BigQuery table using primary keys."""
        table_ref = f"{self.project}.{dataset_id}.{table_id}"

        if df.empty:
            return {"status": "skipped", "table_ref": table_ref, "rows_affected": 0, "mock": self.mock}

        if self.mock or self._client is None:
            existing = self._mock_tables.get(table_ref, pd.DataFrame())
            if (
                existing.empty
                or not primary_keys
                or not all(k in df.columns and k in existing.columns for k in primary_keys)
            ):
                self._mock_tables[table_ref] = df.copy()
            else:
                # Mock MERGE logic: remove existing rows matching primary keys, then append new rows
                cond = pd.Series([True] * len(existing))
                for key in primary_keys:
                    cond = cond & (existing[key].isin(df[key]))
                filtered = existing[~cond]
                merged = pd.concat([filtered, df], ignore_index=True)
                self._mock_tables[table_ref] = merged

            logger.info(f"[MOCK BQ] Merged {len(df)} rows into `{table_ref}` on PKs: {primary_keys}")
            return {
                "status": "success",
                "table_ref": table_ref,
                "rows_affected": len(df),
                "operation": "MERGE",
                "mock": True,
            }

        # Real BigQuery MERGE using temporary staging table
        temp_table_id = f"_temp_stage_{table_id}_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}"
        self.write_dataframe(df, dataset_id, temp_table_id, write_disposition="WRITE_TRUNCATE")

        temp_ref = f"{self.project}.{dataset_id}.{temp_table_id}"
        on_clause = " AND ".join([f"T.{col} = S.{col}" for col in primary_keys])
        update_cols = [c for c in df.columns if c not in primary_keys]
        update_clause = (
            ", ".join([f"T.{c} = S.{c}" for c in update_cols])
            if update_cols
            else f"T.{primary_keys[0]} = S.{primary_keys[0]}"
        )
        insert_cols = ", ".join(df.columns)
        insert_vals = ", ".join([f"S.{c}" for c in df.columns])

        merge_sql = f"""
        MERGE INTO `{table_ref}` T
        USING `{temp_ref}` S
        ON {on_clause}
        WHEN MATCHED THEN
          UPDATE SET {update_clause}
        WHEN NOT MATCHED THEN
          INSERT ({insert_cols}) VALUES ({insert_vals});
        """

        try:
            query_job = self._client.query(merge_sql)
            query_job.result()
            logger.info(f"✓ BigQuery MERGE completed for `{table_ref}`")
            # Cleanup temp staging table
            self._client.delete_table(temp_ref, not_found_ok=True)
            return {
                "status": "success",
                "table_ref": table_ref,
                "rows_affected": len(df),
                "operation": "MERGE",
                "mock": False,
            }
        except Exception as exc:
            self._client.delete_table(temp_ref, not_found_ok=True)
            raise RuntimeError(f"BigQuery MERGE failed for `{table_ref}`: {exc}") from exc
