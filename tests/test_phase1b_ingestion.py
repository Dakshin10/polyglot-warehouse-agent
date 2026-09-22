"""Unit and integration tests for Phase 1B Enterprise Ingestion & BigQuery Data Foundation.

Executes 100% offline using mock connectors and BigQueryWriter fakes, requiring zero GCP cloud credentials.
"""

from __future__ import annotations

import logging
import pandas as pd

from pwa.control_plane.metadata import ControlPlaneManager
from pwa.control_plane.watermark import WatermarkManager
from pwa.governance.schema_evolution import SchemaEvolutionEngine
from pwa.ingestion.connectors.base import SchemaColumn, TableSchema
from pwa.ingestion.connectors.postgres_connector import PostgreSQLConnector
from pwa.quality.reconciliation import SourceTargetReconciler
from pwa.warehouse.bigquery.writer import BigQueryWriter
from pwa.warehouse.staging.staging_processor import StagingProcessor


# ---------------------------------------------------------------------------
# Test 1: Watermark Advances On Success
# ---------------------------------------------------------------------------
def test_watermark_advances_on_success():
    writer = BigQueryWriter(mock=True)
    wm_mgr = WatermarkManager(writer=writer)

    advanced = wm_mgr.advance_watermark(
        source_id="d1",
        table_name="employees",
        watermark_col="modified_date",
        new_watermark="2026-09-01",
        run_id="run-100",
        extraction_ok=True,
        transformation_ok=True,
        quality_ok=True,
        commit_ok=True,
        reconciliation_ok=True,
    )

    assert advanced is True
    assert wm_mgr.get_watermark("d1", "employees") == "2026-09-01"


# ---------------------------------------------------------------------------
# Test 2: Failed Extraction Does NOT Advance Watermark
# ---------------------------------------------------------------------------
def test_failed_extraction_does_not_advance_watermark():
    writer = BigQueryWriter(mock=True)
    wm_mgr = WatermarkManager(writer=writer)

    wm_mgr.advance_watermark(
        source_id="d1",
        table_name="employees",
        watermark_col="mod",
        new_watermark="2026-01-01",
        run_id="r0",
        extraction_ok=True,
        transformation_ok=True,
        quality_ok=True,
        commit_ok=True,
    )

    advanced = wm_mgr.advance_watermark(
        source_id="d1",
        table_name="employees",
        watermark_col="mod",
        new_watermark="2026-09-01",
        run_id="r1",
        extraction_ok=False,
        transformation_ok=True,
        quality_ok=True,
        commit_ok=True,
    )

    assert advanced is False
    assert wm_mgr.get_watermark("d1", "employees") == "2026-01-01"


# ---------------------------------------------------------------------------
# Test 3: Failed Quality Check Does NOT Advance Watermark
# ---------------------------------------------------------------------------
def test_failed_quality_check_does_not_advance_watermark():
    writer = BigQueryWriter(mock=True)
    wm_mgr = WatermarkManager(writer=writer)

    advanced = wm_mgr.advance_watermark(
        source_id="alloydb",
        table_name="products",
        watermark_col="updated_at",
        new_watermark="2026-09-01",
        run_id="r2",
        extraction_ok=True,
        transformation_ok=True,
        quality_ok=False,
        commit_ok=True,
    )

    assert advanced is False
    assert wm_mgr.get_watermark("alloydb", "products") is None


# ---------------------------------------------------------------------------
# Test 4: Failed Warehouse Commit Does NOT Advance Watermark
# ---------------------------------------------------------------------------
def test_failed_warehouse_commit_does_not_advance_watermark():
    writer = BigQueryWriter(mock=True)
    wm_mgr = WatermarkManager(writer=writer)

    advanced = wm_mgr.advance_watermark(
        source_id="aiven_mysql",
        table_name="suppliers",
        watermark_col="load_timestamp",
        new_watermark="2026-09-01",
        run_id="r3",
        extraction_ok=True,
        transformation_ok=True,
        quality_ok=True,
        commit_ok=False,
    )

    assert advanced is False
    assert wm_mgr.get_watermark("aiven_mysql", "suppliers") is None


# ---------------------------------------------------------------------------
# Test 5: Idempotent Ingestion - No Duplicates
# ---------------------------------------------------------------------------
def test_idempotent_ingestion_no_duplicates():
    raw_df = pd.DataFrame(
        [
            {"CustomerID": 1001, "Account": "AW01", "Name": "Acme Corp"},
            {"CustomerID": 1001, "Account": "AW01", "Name": "Acme Corp"},  # Duplicate
            {"CustomerID": 1002, "Account": "AW02", "Name": "Beta LLC"},
        ]
    )

    writer = BigQueryWriter(mock=True)
    sp = StagingProcessor(writer=writer)
    res = sp.process_table(raw_df, source_system="adventureworks", table_name="customers", primary_key="CustomerID")

    assert res["status"] == "success"
    stg_df = writer.get_table_dataframe(sp.ds_enterprise, "stg_adventureworks_customers")
    assert len(stg_df) == 2  # Duplicate removed


# ---------------------------------------------------------------------------
# Test 6: Schema Evolution - Compatible Column Added
# ---------------------------------------------------------------------------
def test_schema_evolution_compatible_column_added():
    writer = BigQueryWriter(mock=True)
    engine = SchemaEvolutionEngine(writer=writer)

    prev_schema = TableSchema(
        table_name="orders",
        columns=[SchemaColumn("order_id", "integer", is_pk=True), SchemaColumn("total", "real")],
        primary_key=["order_id"],
    )

    curr_schema = TableSchema(
        table_name="orders",
        columns=[
            SchemaColumn("order_id", "integer", is_pk=True),
            SchemaColumn("total", "real"),
            SchemaColumn("discount", "real"),  # New column added
        ],
        primary_key=["order_id"],
    )

    eval_res = engine.evaluate_schema_change("alloydb", "orders", curr_schema, prev_schema, run_id="r-schema")
    assert eval_res["status"] == "ALLOWED"
    assert any("New column detected" in c for c in eval_res["changes"])


# ---------------------------------------------------------------------------
# Test 7: Schema Evolution - Incompatible Type Blocked
# ---------------------------------------------------------------------------
def test_schema_evolution_incompatible_type_blocked():
    writer = BigQueryWriter(mock=True)
    engine = SchemaEvolutionEngine(writer=writer)

    prev_schema = TableSchema(
        table_name="orders",
        columns=[SchemaColumn("order_date", "text")],
        primary_key=[],
    )

    curr_schema = TableSchema(
        table_name="orders",
        columns=[SchemaColumn("order_date", "boolean")],  # Incompatible change text -> boolean
        primary_key=[],
    )

    eval_res = engine.evaluate_schema_change("alloydb", "orders", curr_schema, prev_schema, run_id="r-schema-bad")
    assert eval_res["status"] == "BLOCKED"
    assert len(eval_res["errors"]) > 0


# ---------------------------------------------------------------------------
# Test 8: Source-Target Reconciliation Detects Mismatch
# ---------------------------------------------------------------------------
def test_reconciliation_detects_mismatch():
    reconciler = SourceTargetReconciler()
    match_res = reconciler.reconcile_counts("d1", "employees", source_count=15, target_count=15)
    assert match_res["status"] == "PASS"

    mismatch_res = reconciler.reconcile_counts("d1", "employees", source_count=15, target_count=10)
    assert mismatch_res["status"] == "FAIL"
    assert mismatch_res["diff"] == 5


# ---------------------------------------------------------------------------
# Test 9: Secrets Never Logged
# ---------------------------------------------------------------------------
def test_secrets_never_logged(caplog):
    pg_conn = PostgreSQLConnector(
        "test_pg",
        {"host": "localhost", "user": "db_user", "password": "SUPER_SECRET_PASSWORD_123!", "database": "test_db"},
    )

    with caplog.at_level(logging.DEBUG):
        pg_conn._should_use_fallback()
        try:
            pg_conn.connect()
        except Exception:
            pass

    log_text = caplog.text
    assert "SUPER_SECRET_PASSWORD_123!" not in log_text


# ---------------------------------------------------------------------------
# Test 10: Run Metadata Records Failure Correctly
# ---------------------------------------------------------------------------
def test_run_metadata_records_failure():
    writer = BigQueryWriter(mock=True)
    cp_mgr = ControlPlaneManager(writer=writer)

    cp_mgr.start_pipeline_run("run-fail-1", "aiven_mysql", mode="snapshot")
    cp_mgr.finish_pipeline_run(
        "run-fail-1", status="FAILED", total_rows_extracted=50, total_rows_loaded=0, error_message="Connection timeout"
    )

    df = writer.get_table_dataframe(cp_mgr.dataset_id, "pwa_pipeline_runs")
    assert not df.empty
    failed_runs = df[df["status"] == "FAILED"]
    assert len(failed_runs) > 0
    assert failed_runs["error_message"].iloc[0] == "Connection timeout"
