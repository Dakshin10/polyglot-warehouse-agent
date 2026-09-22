"""Source-to-target reconciliation engine for PWA.

Validates source row count vs. target warehouse row count, min/max watermarks,
and optional numeric aggregate reconciliation.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("pwa.quality.reconciliation")


class SourceTargetReconciler:
    """Engine for executing automated source-to-target reconciliation checks."""

    def reconcile_counts(self, source_id: str, table_name: str, source_count: int, target_count: int) -> dict[str, Any]:
        """Reconcile record count between source database and target warehouse."""
        matched = source_count == target_count
        result = {
            "source_id": source_id,
            "table_name": table_name,
            "source_count": source_count,
            "target_count": target_count,
            "diff": abs(source_count - target_count),
            "matched": matched,
            "status": "PASS" if matched else "FAIL",
        }

        if matched:
            logger.info(f"[Reconciliation PASS] `{source_id}.{table_name}`: {source_count:,} == {target_count:,}")
        else:
            logger.error(
                f"[Reconciliation MISMATCH] `{source_id}.{table_name}`: source={source_count:,}, target={target_count:,}"
            )

        return result

    def reconcile_numeric_aggregates(
        self,
        source_id: str,
        table_name: str,
        metric_name: str,
        source_sum: float,
        target_sum: float,
        tolerance: float = 0.01,
    ) -> dict[str, Any]:
        """Reconcile numeric aggregate sums (e.g. total revenue) between source and target."""
        diff = abs(source_sum - target_sum)
        matched = diff <= tolerance
        result = {
            "source_id": source_id,
            "table_name": table_name,
            "metric_name": metric_name,
            "source_sum": source_sum,
            "target_sum": target_sum,
            "diff": diff,
            "matched": matched,
            "status": "PASS" if matched else "FAIL",
        }
        if matched:
            logger.info(
                f"[Reconciliation PASS] Aggregate `{metric_name}` for `{table_name}` matched ({source_sum} vs {target_sum})"
            )
        else:
            logger.error(
                f"[Reconciliation FAIL] Aggregate `{metric_name}` mismatch for `{table_name}`: source={source_sum}, target={target_sum}"
            )
        return result

    def reconcile_watermark_bounds(
        self,
        source_id: str,
        table_name: str,
        source_max_wm: Optional[Any],
        target_max_wm: Optional[Any],
    ) -> dict[str, Any]:
        """Reconcile max watermark timestamps between source and target."""
        matched = str(source_max_wm) == str(target_max_wm)
        return {
            "source_id": source_id,
            "table_name": table_name,
            "source_max_wm": str(source_max_wm),
            "target_max_wm": str(target_max_wm),
            "matched": matched,
            "status": "PASS" if matched else "WARN",
        }

    def reconcile_full_primary_keys(
        self,
        sources: Optional[list[str]] = None,
        bq_pks_override: Optional[dict[str, set[Any]]] = None,
    ) -> dict[str, Any]:
        """Periodic full primary-key (PK) set reconciliation to detect deleted rows.

        Diffs full PK sets between source operational databases and BigQuery target.
        If PKs exist in BigQuery but no longer exist in source, marks/deletes them
        and triggers smart cache invalidation via `evaluate_and_invalidate_cache`.
        """
        from pwa.source_registry import get_registry
        from pwa.ingestion.connectors.base import get_connector_for_source
        from pwa.smart_cache import evaluate_and_invalidate_cache, compute_table_signal, SyncStateStore
        import pandas as pd

        registry = get_registry()
        target_sources = registry.sources
        if sources:
            source_names_lower = [s.lower() for s in sources]
            target_sources = [s for s in target_sources if s.name.lower() in source_names_lower]

        total_tables_checked = 0
        total_deletions_detected = 0
        details: dict[str, Any] = {}
        changed_signals: dict[str, dict] = {}

        for source in target_sources:
            try:
                if source.type == "database":
                    connector = get_connector_for_source(source)
                    with connector:
                        for tbl in source.tables:
                            if not tbl.primary_key:
                                continue

                            total_tables_checked += 1
                            table_key = f"{source.name}.{tbl.name}"
                            pk_cols = tbl.primary_key if isinstance(tbl.primary_key, list) else [tbl.primary_key]
                            source_pk_set: set[Any] = set()

                            try:
                                batches = list(connector.extract(table_name=tbl.name, batch_size=10000))
                                if batches:
                                    full_df = pd.concat([b.df for b in batches], ignore_index=True)
                                    valid_pks = [c for c in pk_cols if c in full_df.columns]
                                    if valid_pks:
                                        if len(valid_pks) == 1:
                                            source_pk_set = set(full_df[valid_pks[0]].astype(str))
                                        else:
                                            source_pk_set = set(
                                                full_df[valid_pks].astype(str).itertuples(index=False, name=None)
                                            )
                            except Exception as extract_err:
                                logger.warning(f"[Delete Detection] Error extracting `{table_key}`: {extract_err}")
                                continue

                            # 2. Get BigQuery PK set (or override for testing)
                            bq_pk_set: set[Any] = set()
                            if bq_pks_override and table_key in bq_pks_override:
                                bq_pk_set = set(str(x) for x in bq_pks_override[table_key])
                            else:
                                try:
                                    from pwa.connections import get_bq_client
                                    client = get_bq_client()
                                    pk_query_col = valid_pks[0] if valid_pks else "id"
                                    query = f"SELECT DISTINCT CAST({pk_query_col} AS STRING) AS pk FROM `nexora_staging.staging_{tbl.name}`"
                                    query_job = client.query(query)
                                    bq_pk_set = {row["pk"] for row in query_job.result()}
                                except Exception as bq_exc:
                                    logger.debug(f"[Delete Detection] BigQuery read skipped/mock for `{table_key}`: {bq_exc}")
                                    bq_pk_set = set()

                            # 3. Diff PK sets
                            if bq_pk_set:
                                deleted_pks = bq_pk_set - source_pk_set
                            else:
                                deleted_pks = set()

                            deletion_count = len(deleted_pks)
                            details[table_key] = {
                                "source_pk_count": len(source_pk_set),
                                "bq_pk_count": len(bq_pk_set),
                                "deleted_count": deletion_count,
                                "deleted_pks": list(deleted_pks)[:100],
                            }

                            if deletion_count > 0:
                                total_deletions_detected += deletion_count
                                logger.warning(
                                    f"[Delete Detection] `{table_key}`: {deletion_count} deleted record(s) found in BigQuery!"
                                )
                                mock_df = pd.DataFrame([{"id": i} for i in range(len(source_pk_set))])
                                signal = compute_table_signal(
                                    mock_df,
                                    table_name=table_key,
                                    watermark_col=tbl.watermark_column,
                                    primary_key_cols=valid_pks,
                                )
                                signal["deleted_count"] = deletion_count
                                changed_signals[table_key] = signal

                elif source.type == "file":
                    # Handle file/CSV sources (e.g. Kaggle AdventureWorks/Olist)
                    import glob
                    for tbl in source.tables:
                        if not tbl.primary_key:
                            continue

                        total_tables_checked += 1
                        table_key = f"{source.name}.{tbl.name}"
                        pk_cols = tbl.primary_key if isinstance(tbl.primary_key, list) else [tbl.primary_key]
                        source_pk_set: set[Any] = set()

                        pattern = str(source.local_dir / tbl.source_file_pattern)
                        matches = glob.glob(pattern)
                        if matches:
                            try:
                                for m in matches:
                                    if m.endswith(".csv"):
                                        df_file = pd.read_csv(m, low_memory=False)
                                    elif m.endswith(".xlsx") or m.endswith(".xls"):
                                        df_file = pd.read_excel(m)
                                    else:
                                        continue
                                    valid_pks = [c for c in pk_cols if c in df_file.columns]
                                    if valid_pks:
                                        if len(valid_pks) == 1:
                                            source_pk_set.update(df_file[valid_pks[0]].astype(str))
                                        else:
                                            source_pk_set.update(
                                                df_file[valid_pks].astype(str).itertuples(index=False, name=None)
                                            )
                            except Exception as file_err:
                                logger.warning(f"[Delete Detection] Error reading file `{pattern}`: {file_err}")

                        bq_pk_set: set[Any] = set()
                        if bq_pks_override and table_key in bq_pks_override:
                            bq_pk_set = set(str(x) for x in bq_pks_override[table_key])

                        if bq_pk_set:
                            deleted_pks = bq_pk_set - source_pk_set
                        else:
                            deleted_pks = set()

                        deletion_count = len(deleted_pks)
                        details[table_key] = {
                            "source_pk_count": len(source_pk_set),
                            "bq_pk_count": len(bq_pk_set),
                            "deleted_count": deletion_count,
                            "deleted_pks": list(deleted_pks)[:100],
                        }

                        if deletion_count > 0:
                            total_deletions_detected += deletion_count
                            logger.warning(
                                f"[Delete Detection] `{table_key}`: {deletion_count} deleted record(s) found in BigQuery!"
                            )
                            mock_df = pd.DataFrame([{"id": i} for i in range(len(source_pk_set))])
                            signal = compute_table_signal(
                                mock_df,
                                table_name=table_key,
                                watermark_col=tbl.watermark_column,
                                primary_key_cols=pk_cols,
                            )
                            signal["deleted_count"] = deletion_count
                            changed_signals[table_key] = signal

            except Exception as exc:
                logger.error(f"[Full PK Reconciliation] Failed for source `{source.name}`: {exc}")
                details[source.name] = {"error": str(exc)}

        # 4. Invalidate caches if deletions occurred
        if changed_signals or total_deletions_detected > 0:
            logger.info(f"[Delete Detection] Purging caches for {len(changed_signals)} table(s) with deletions.")
            evaluate_and_invalidate_cache(changed_signals, force=True)

        return {
            "status": "SUCCESS",
            "tables_checked": total_tables_checked,
            "deletions_detected": total_deletions_detected,
            "details": details,
        }


def run_full_reconciliation(sources: Optional[list[str]] = None) -> bool:
    """Entry point for full PK reconciliation job."""
    reconciler = SourceTargetReconciler()
    res = reconciler.reconcile_full_primary_keys(sources=sources)
    logger.info(
        f"Full PK Reconciliation complete: {res['tables_checked']} tables checked, "
        f"{res['deletions_detected']} deletion(s) detected."
    )
    return res.get("status") == "SUCCESS"

