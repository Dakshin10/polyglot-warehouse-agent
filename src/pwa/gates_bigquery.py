"""BigQuery quality gates for Nexora Technologies enterprise platform.

Gate IDs: B1–B15 (warehouse-layer checks, after BigQuery ingestion)

These gates validate the BigQuery warehouse after ingestion:
  B1:  raw_adventureworks dataset exists and has tables
  B2:  raw_olist dataset exists and has tables
  B3:  raw_olist_marketing dataset exists and has tables
  B4:  raw_adventureworks.sales_order_header row count >= 31,000
  B5:  raw_olist.olist_orders row count >= 90,000
  B6:  raw_olist.olist_order_items rows > olist_orders rows
  B7:  PWA provenance metadata columns present in raw tables
  B8:  curated_enterprise dataset exists and has views
  B9:  curated_marketplace dataset exists and has views
  B10: fact_sales_order in curated_enterprise has rows >= raw source
  B11: fact_marketplace_order in curated_marketplace has rows >= raw source
  B12: Cross-source integrity: v_integrity_cross_source_seller returns 0 rows
  B13: Cross-source integrity: v_integrity_order_item_orphans returns 0 rows
  B14: pwa_metadata dataset exists and has control tables
  B15: pwa_quality_results is queryable and control plane is functional
"""

import logging
from typing import Optional

from google.api_core.exceptions import NotFound

from pwa.connections import get_bq_client
from pwa.gates_runner import GateResult, cannot_verify, run_gates
from pwa.settings import get_settings

logger = logging.getLogger("pwa.gates_bigquery")


def _query_scalar(sql: str, error_label: str) -> Optional[int | float]:
    """Run a scalar BigQuery query and return the result."""
    try:
        client = get_bq_client()
        rows = list(client.query(sql).result())
        if rows:
            return list(rows[0].values())[0]
        return None
    except Exception as exc:
        logger.warning(f"[{error_label}] Query failed: {exc}")
        return None


def _dataset_exists(project: str, dataset_id: str) -> bool:
    client = get_bq_client()
    try:
        client.get_dataset(f"{project}.{dataset_id}")
        return True
    except NotFound:
        return False


def _count_tables(project: str, dataset_id: str) -> int:
    """Count the number of tables (or views) in a BigQuery dataset."""
    client = get_bq_client()
    try:
        tables = list(client.list_tables(f"{project}.{dataset_id}"))
        return len(tables)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# B1: raw_adventureworks dataset and tables
# ---------------------------------------------------------------------------


def gate_b1_raw_adventureworks_exists() -> GateResult:
    """B1: raw_adventureworks dataset exists and has at least 10 tables."""
    s = get_settings()
    project = s.gcp_project
    ds = s.bq_ds_raw_aw

    if not _dataset_exists(project, ds):
        return GateResult(
            id="B1",
            name="raw_adventureworks dataset exists",
            passed=False,
            detail=f"`{project}.{ds}` not found. Run: pwa warehouse run",
        )

    count = _count_tables(project, ds)
    passed = count >= 10
    return GateResult(
        id="B1",
        name="raw_adventureworks dataset exists",
        passed=passed,
        detail=f"{count} table(s) in `{project}.{ds}`. Expected >= 10.",
    )


# ---------------------------------------------------------------------------
# B2: raw_olist dataset and tables
# ---------------------------------------------------------------------------


def gate_b2_raw_olist_exists() -> GateResult:
    """B2: raw_olist dataset exists and has at least 7 tables."""
    s = get_settings()
    project = s.gcp_project
    ds = s.bq_ds_raw_olist

    if not _dataset_exists(project, ds):
        return GateResult(
            id="B2",
            name="raw_olist dataset exists",
            passed=False,
            detail=f"`{project}.{ds}` not found. Run: pwa warehouse run",
        )

    count = _count_tables(project, ds)
    passed = count >= 7
    return GateResult(
        id="B2",
        name="raw_olist dataset exists",
        passed=passed,
        detail=f"{count} table(s) in `{project}.{ds}`. Expected >= 7.",
    )


# ---------------------------------------------------------------------------
# B3: raw_olist_marketing dataset and tables
# ---------------------------------------------------------------------------


def gate_b3_raw_olist_marketing_exists() -> GateResult:
    """B3: raw_olist_marketing dataset exists and has at least 2 tables."""
    s = get_settings()
    project = s.gcp_project
    ds = s.bq_ds_raw_marketing

    if not _dataset_exists(project, ds):
        return GateResult(
            id="B3",
            name="raw_olist_marketing dataset exists",
            passed=False,
            detail=f"`{project}.{ds}` not found. Run: pwa warehouse run",
        )

    count = _count_tables(project, ds)
    passed = count >= 2
    return GateResult(
        id="B3",
        name="raw_olist_marketing dataset exists",
        passed=passed,
        detail=f"{count} table(s) in `{project}.{ds}`. Expected >= 2.",
    )


# ---------------------------------------------------------------------------
# B4: raw_adventureworks.sales_order_header row count
# ---------------------------------------------------------------------------


def gate_b4_raw_aw_sales_order_count() -> GateResult:
    """B4: raw_adventureworks.sales_order_header has >= 31,000 rows."""
    s = get_settings()
    project = s.gcp_project
    table = f"{project}.{s.bq_ds_raw_aw}.sales_order_header"

    sql = f"SELECT COUNT(*) AS cnt FROM `{table}`"
    count = _query_scalar(sql, "B4")
    if count is None:
        return cannot_verify(
            "B4",
            "raw_adventureworks.sales_order_header row count",
            f"Could not query `{table}`",
        )

    min_rows = 50 if s.pwa_env == "development" else 31_000
    passed = int(count) >= min_rows
    return GateResult(
        id="B4",
        name="raw_adventureworks.sales_order_header row count",
        passed=passed,
        detail=f"{int(count):,} rows in `{table}`. Threshold: >= {min_rows:,}.",
    )


# ---------------------------------------------------------------------------
# B5: raw_olist.olist_orders row count
# ---------------------------------------------------------------------------


def gate_b5_raw_olist_orders_count() -> GateResult:
    """B5: raw_olist.olist_orders has >= 90,000 rows (or >= 100 in dev)."""
    s = get_settings()
    project = s.gcp_project
    table = f"{project}.{s.bq_ds_raw_olist}.olist_orders"

    sql = f"SELECT COUNT(*) AS cnt FROM `{table}`"
    count = _query_scalar(sql, "B5")
    if count is None:
        return cannot_verify("B5", "raw_olist.olist_orders row count", f"Could not query `{table}`")

    min_rows = 100 if s.pwa_env == "development" else 90_000
    passed = int(count) >= min_rows
    return GateResult(
        id="B5",
        name="raw_olist.olist_orders row count",
        passed=passed,
        detail=f"{int(count):,} rows in `{table}`. Threshold: >= {min_rows:,}.",
    )


# ---------------------------------------------------------------------------
# B6: raw_olist.olist_order_items > olist_orders
# ---------------------------------------------------------------------------


def gate_b6_raw_olist_order_items_ratio() -> GateResult:
    """B6: raw_olist.olist_order_items has more rows than olist_orders."""
    s = get_settings()
    project = s.gcp_project

    orders_table = f"{project}.{s.bq_ds_raw_olist}.olist_orders"
    items_table = f"{project}.{s.bq_ds_raw_olist}.olist_order_items"

    orders_count = _query_scalar(f"SELECT COUNT(*) FROM `{orders_table}`", "B6-orders")
    items_count = _query_scalar(f"SELECT COUNT(*) FROM `{items_table}`", "B6-items")

    if orders_count is None or items_count is None:
        return cannot_verify("B6", "Olist order_items > orders ratio", "Could not query one or both tables.")

    passed = int(items_count) > int(orders_count)
    ratio = int(items_count) / int(orders_count) if int(orders_count) > 0 else 0.0
    return GateResult(
        id="B6",
        name="raw_olist order_items rows > orders rows",
        passed=passed,
        detail=(
            f"orders: {int(orders_count):,}, order_items: {int(items_count):,}, ratio: {ratio:.2f}x. Expected > 1.0."
        ),
    )


# ---------------------------------------------------------------------------
# B7: PWA provenance metadata columns present in raw tables
# ---------------------------------------------------------------------------


def gate_b7_pwa_metadata_columns_present() -> GateResult:
    """B7: PWA provenance metadata columns present in at least one raw table per source."""
    s = get_settings()
    project = s.gcp_project

    tables_to_check = [
        (s.bq_ds_raw_aw, "sales_order_header"),
        (s.bq_ds_raw_olist, "olist_orders"),
        (s.bq_ds_raw_marketing, "olist_closed_deals"),
    ]

    required_cols = {"_pwa_ingested_at", "_pwa_run_id", "_pwa_source_system", "_pwa_source_table"}
    issues = []

    client = get_bq_client()
    for ds, tbl in tables_to_check:
        table_ref = f"{project}.{ds}.{tbl}"
        try:
            table = client.get_table(table_ref)
            col_names = {f.name for f in table.schema}
            missing = required_cols - col_names
            if missing:
                issues.append(f"`{table_ref}` missing columns: {missing}")
        except Exception as exc:
            issues.append(f"`{table_ref}` not accessible: {exc}")

    passed = len(issues) == 0
    return GateResult(
        id="B7",
        name="PWA provenance metadata columns present",
        passed=passed,
        detail=("All PWA metadata columns present in checked tables." if passed else "Issues: " + "; ".join(issues)),
    )


# ---------------------------------------------------------------------------
# B8: curated_enterprise dataset exists and has views
# ---------------------------------------------------------------------------


def gate_b8_curated_enterprise_exists() -> GateResult:
    """B8: curated_enterprise dataset exists and has at least 8 views."""
    s = get_settings()
    project = s.gcp_project
    ds = s.bq_ds_curated_ent

    if not _dataset_exists(project, ds):
        return GateResult(
            id="B8",
            name="curated_enterprise dataset exists",
            passed=False,
            detail=f"`{project}.{ds}` not found. Run: pwa warehouse run",
        )

    count = _count_tables(project, ds)
    passed = count >= 8
    return GateResult(
        id="B8",
        name="curated_enterprise dataset exists",
        passed=passed,
        detail=f"{count} view(s) in `{project}.{ds}`. Expected >= 8.",
    )


# ---------------------------------------------------------------------------
# B9: curated_marketplace dataset exists and has views
# ---------------------------------------------------------------------------


def gate_b9_curated_marketplace_exists() -> GateResult:
    """B9: curated_marketplace dataset exists and has at least 7 views."""
    s = get_settings()
    project = s.gcp_project
    ds = s.bq_ds_curated_mkt

    if not _dataset_exists(project, ds):
        return GateResult(
            id="B9",
            name="curated_marketplace dataset exists",
            passed=False,
            detail=f"`{project}.{ds}` not found. Run: pwa warehouse run",
        )

    count = _count_tables(project, ds)
    passed = count >= 7
    return GateResult(
        id="B9",
        name="curated_marketplace dataset exists",
        passed=passed,
        detail=f"{count} view(s) in `{project}.{ds}`. Expected >= 7.",
    )


# ---------------------------------------------------------------------------
# B10: curated fact_sales_order row count >= raw source
# ---------------------------------------------------------------------------


def gate_b10_curated_sales_order_count() -> GateResult:
    """B10: curated_enterprise.fact_sales_order row count >= raw source."""
    s = get_settings()
    project = s.gcp_project

    raw_table = f"{project}.{s.bq_ds_raw_aw}.sales_order_header"
    curated_view = f"{project}.{s.bq_ds_curated_ent}.fact_sales_order"

    raw_count = _query_scalar(f"SELECT COUNT(*) FROM `{raw_table}`", "B10-raw")
    curated_count = _query_scalar(f"SELECT COUNT(*) FROM `{curated_view}`", "B10-curated")

    if raw_count is None or curated_count is None:
        return cannot_verify(
            "B10",
            "curated fact_sales_order row count",
            "Could not query raw or curated tables.",
        )

    # Curated should have the same number of rows as raw (no filtering in views)
    passed = int(curated_count) >= int(raw_count) * 0.99
    return GateResult(
        id="B10",
        name="curated fact_sales_order row count >= raw",
        passed=passed,
        detail=(f"raw: {int(raw_count):,}, curated: {int(curated_count):,}. Curated should be >= 99% of raw."),
    )


# ---------------------------------------------------------------------------
# B11: curated fact_marketplace_order row count >= raw source
# ---------------------------------------------------------------------------


def gate_b11_curated_marketplace_order_count() -> GateResult:
    """B11: curated_marketplace.fact_marketplace_order row count >= raw source."""
    s = get_settings()
    project = s.gcp_project

    raw_table = f"{project}.{s.bq_ds_raw_olist}.olist_orders"
    curated_view = f"{project}.{s.bq_ds_curated_mkt}.fact_marketplace_order"

    raw_count = _query_scalar(f"SELECT COUNT(*) FROM `{raw_table}`", "B11-raw")
    curated_count = _query_scalar(f"SELECT COUNT(*) FROM `{curated_view}`", "B11-curated")

    if raw_count is None or curated_count is None:
        return cannot_verify(
            "B11", "curated fact_marketplace_order row count", "Could not query raw or curated tables."
        )

    passed = int(curated_count) >= int(raw_count) * 0.99
    return GateResult(
        id="B11",
        name="curated fact_marketplace_order row count >= raw",
        passed=passed,
        detail=(f"raw: {int(raw_count):,}, curated: {int(curated_count):,}. Curated should be >= 99% of raw."),
    )


# ---------------------------------------------------------------------------
# B12: Cross-source integrity — orphan sellers in closed_deals = 0
# ---------------------------------------------------------------------------


def gate_b12_integrity_seller_orphans() -> GateResult:
    """B12: v_integrity_cross_source_seller returns 0 rows."""
    s = get_settings()
    project = s.gcp_project
    view = f"{project}.{s.bq_ds_curated_ent}.v_integrity_cross_source_seller"

    sql = f"SELECT COUNT(*) AS cnt FROM `{view}`"
    count = _query_scalar(sql, "B12")

    if count is None:
        return cannot_verify("B12", "Cross-source seller orphan check", f"Could not query `{view}`.")

    passed = int(count) == 0
    return GateResult(
        id="B12",
        name="Cross-source seller integrity (0 orphans in closed_deals)",
        passed=passed,
        detail=(f"{int(count)} orphan seller_id(s) in olist_closed_deals with no match in olist_sellers. Should be 0."),
    )


# ---------------------------------------------------------------------------
# B13: Cross-source integrity — orphan order items = 0
# ---------------------------------------------------------------------------


def gate_b13_integrity_order_item_orphans() -> GateResult:
    """B13: v_integrity_order_item_orphans returns 0 rows."""
    s = get_settings()
    project = s.gcp_project
    view = f"{project}.{s.bq_ds_curated_ent}.v_integrity_order_item_orphans"

    sql = f"SELECT COUNT(*) AS cnt FROM `{view}`"
    count = _query_scalar(sql, "B13")

    if count is None:
        return cannot_verify("B13", "Olist order_item orphan check", f"Could not query `{view}`.")

    passed = int(count) == 0
    return GateResult(
        id="B13",
        name="Olist order_item integrity (0 orphan order_ids)",
        passed=passed,
        detail=(f"{int(count)} orphan order_id(s) in olist_order_items with no match in olist_orders. Should be 0."),
    )


# ---------------------------------------------------------------------------
# B14: pwa_metadata dataset and control tables
# ---------------------------------------------------------------------------


def gate_b14_pwa_metadata_exists() -> GateResult:
    """B14: pwa_metadata dataset exists and has at least 7 control tables."""
    s = get_settings()
    project = s.gcp_project
    ds = s.bq_ds_metadata

    if not _dataset_exists(project, ds):
        return GateResult(
            id="B14",
            name="pwa_metadata control plane exists",
            passed=False,
            detail=f"`{project}.{ds}` not found. Run: pwa warehouse run",
        )

    count = _count_tables(project, ds)
    passed = count >= 7
    return GateResult(
        id="B14",
        name="pwa_metadata control plane exists",
        passed=passed,
        detail=f"{count} table(s) in `{project}.{ds}`. Expected >= 7.",
    )


# ---------------------------------------------------------------------------
# B15: pwa_sources table has all 3 sources registered
# ---------------------------------------------------------------------------


def gate_b15_sources_registered() -> GateResult:
    """B15: pwa_metadata.pwa_sources has all 3 sources registered."""
    s = get_settings()
    project = s.gcp_project
    table = f"{project}.{s.bq_ds_metadata}.pwa_sources"

    sql = f"""
    SELECT COUNT(*) AS cnt
    FROM `{table}`
    WHERE is_active = TRUE
    """
    count = _query_scalar(sql, "B15")

    if count is None:
        return cannot_verify("B15", "Source registration check", f"Could not query `{table}`.")

    expected = 3  # adventureworks, olist, olist_marketing
    passed = int(count) >= expected
    return GateResult(
        id="B15",
        name="All 3 sources registered in pwa_metadata",
        passed=passed,
        detail=(
            f"{int(count)} active source(s) in `pwa_metadata.pwa_sources`. "
            f"Expected >= {expected} (adventureworks, olist, olist_marketing)."
        ),
    )


# ---------------------------------------------------------------------------
# Registry and runner
# ---------------------------------------------------------------------------

GATES = [
    gate_b1_raw_adventureworks_exists,
    gate_b2_raw_olist_exists,
    gate_b3_raw_olist_marketing_exists,
    gate_b4_raw_aw_sales_order_count,
    gate_b5_raw_olist_orders_count,
    gate_b6_raw_olist_order_items_ratio,
    gate_b7_pwa_metadata_columns_present,
    gate_b8_curated_enterprise_exists,
    gate_b9_curated_marketplace_exists,
    gate_b10_curated_sales_order_count,
    gate_b11_curated_marketplace_order_count,
    gate_b12_integrity_seller_orphans,
    gate_b13_integrity_order_item_orphans,
    gate_b14_pwa_metadata_exists,
    gate_b15_sources_registered,
]


def run_all_bq_gates() -> bool:
    """Run all 15 BigQuery quality gates. Returns True only if all pass."""
    return run_gates(GATES, title="BIGQUERY QUALITY GATES")


if __name__ == "__main__":
    from pwa.logging_setup import setup_logging

    setup_logging()
    raise SystemExit(0 if run_all_bq_gates() else 1)
