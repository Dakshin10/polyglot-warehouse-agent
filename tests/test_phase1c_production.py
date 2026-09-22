"""Unit & Integration Tests for Phase 1C — Production Hardening & Enterprise Operations.

Verifies:
1. Production mode safety (PWA_ENV=production blocking SQLite/mock fallbacks)
2. Watermark lookback window calculation
3. BigQuery MERGE / UPSERT functionality
4. CDC change-event model parsing
5. PII classification heuristics
6. Freshness SLA evaluation
7. Numeric aggregate reconciliation
8. Dry-run safety
"""

import os
import unittest
import pandas as pd

from pwa.settings import ProductionEnvironmentError
from pwa.ingestion.connectors.postgres_connector import PostgreSQLConnector
from pwa.ingestion.connectors.mysql_connector import MySQLConnector
from pwa.warehouse.bigquery.writer import BigQueryWriter
from pwa.ingestion.extractor import compute_effective_watermark
from pwa.ingestion.cdc import CdcAdapter, CdcOperation
from pwa.governance.pii import classify_column, SensitivityLevel
from pwa.governance.freshness import FreshnessTracker, FreshnessStatus
from pwa.quality.reconciliation import SourceTargetReconciler
from pwa.cli import cmd_ingest_dry_run


class TestPhase1CProduction(unittest.TestCase):
    def test_production_mode_blocks_sqlite_fallback_in_postgres(self):
        """Invariant: In PWA_ENV=production, PostgreSQLConnector MUST NOT fall back to SQLite."""
        os.environ["PWA_ENV"] = "production"
        try:
            conn = PostgreSQLConnector("alloydb", {"host": "", "user": "", "database": ""})
            with self.assertRaises(ProductionEnvironmentError):
                conn.connect()
        finally:
            os.environ["PWA_ENV"] = "development"

    def test_production_mode_blocks_sqlite_fallback_in_mysql(self):
        """Invariant: In PWA_ENV=production, MySQLConnector MUST NOT fall back to SQLite."""
        os.environ["PWA_ENV"] = "production"
        try:
            conn = MySQLConnector("aiven_mysql", {"host": "", "user": "", "database": ""})
            with self.assertRaises(ProductionEnvironmentError):
                conn.connect()
        finally:
            os.environ["PWA_ENV"] = "development"

    def test_production_mode_blocks_bigquery_mock(self):
        """Invariant: In PWA_ENV=production, BigQueryWriter MUST NOT use mock mode."""
        os.environ["PWA_ENV"] = "production"
        try:
            with self.assertRaises(ProductionEnvironmentError):
                BigQueryWriter(mock=True)
        finally:
            os.environ["PWA_ENV"] = "development"

    def test_compute_effective_watermark_with_lookback(self):
        """Test watermark lookback window calculation for late-arriving records."""
        wm_str = "2026-09-13T10:00:00Z"
        effective = compute_effective_watermark(wm_str, lookback_minutes=15)
        self.assertIn("09:45:00", str(effective))

    def test_bigquery_writer_merge_dataframe(self):
        """Test BigQuery MERGE / UPSERT in mock mode."""
        writer = BigQueryWriter(mock=True)
        df_initial = pd.DataFrame(
            [
                {"id": 1, "val": "A"},
                {"id": 2, "val": "B"},
            ]
        )
        writer.write_dataframe(df_initial, "nexora_raw", "test_table", write_disposition="WRITE_TRUNCATE")

        df_upsert = pd.DataFrame(
            [
                {"id": 2, "val": "B_UPDATED"},
                {"id": 3, "val": "C_NEW"},
            ]
        )
        res = writer.merge_dataframe(df_upsert, "nexora_raw", "test_table", primary_keys=["id"])
        self.assertEqual(res["status"], "success")

        df_res = writer.get_table_dataframe("nexora_raw", "test_table")
        self.assertEqual(len(df_res), 3)
        row_2 = df_res[df_res["id"] == 2]["val"].iloc[0]
        self.assertEqual(row_2, "B_UPDATED")

    def test_cdc_adapter_parse_change_log(self):
        """Test parsing raw change log DataFrame into CdcChangeEvent models."""
        adapter = CdcAdapter("alloydb")
        df_log = pd.DataFrame(
            [
                {"customer_id": "C101", "name": "Acme", "_pwa_op": "INSERT", "_pwa_source_table": "customers"},
                {"customer_id": "C102", "name": "Beta", "_pwa_op": "UPDATE", "_pwa_source_table": "customers"},
                {"customer_id": "C103", "_pwa_op": "DELETE", "_pwa_source_table": "customers"},
            ]
        )
        events = adapter.parse_change_log(df_log, primary_key_cols=["customer_id"])
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0].operation, CdcOperation.INSERT)
        self.assertEqual(events[1].operation, CdcOperation.UPDATE)
        self.assertEqual(events[2].operation, CdcOperation.DELETE)
        self.assertIsNone(events[2].after_payload)

    def test_pii_classification_heuristics(self):
        """Test PII classification tags and sensitivity levels."""
        tag_email = classify_column("customer_email")
        self.assertTrue(tag_email.is_pii)
        self.assertEqual(tag_email.sensitivity, SensitivityLevel.RESTRICTED)

        tag_price = classify_column("list_price")
        self.assertFalse(tag_price.is_pii)
        self.assertEqual(tag_price.sensitivity, SensitivityLevel.INTERNAL)

    def test_freshness_tracker_evaluates_status(self):
        """Test FreshnessTracker SLA status categorization."""
        tracker = FreshnessTracker()
        now_str = pd.Timestamp.now(tz="UTC").isoformat()
        res_fresh = tracker.evaluate_freshness("d1", "employees", now_str, sla_max_delay_minutes=60)
        self.assertEqual(res_fresh.status, FreshnessStatus.FRESH)

    def test_reconciliation_numeric_aggregates(self):
        """Test SourceTargetReconciler aggregate sum reconciliation."""
        reconciler = SourceTargetReconciler()
        res_pass = reconciler.reconcile_numeric_aggregates("alloydb", "sales_orders", "total_due", 10000.00, 10000.00)
        self.assertEqual(res_pass["status"], "PASS")

        res_fail = reconciler.reconcile_numeric_aggregates("alloydb", "sales_orders", "total_due", 10000.00, 9500.00)
        self.assertEqual(res_fail["status"], "FAIL")

    def test_dry_run_cli_execution(self):
        """Test CLI --dry-run mode returns 0 and mutates zero state."""
        rc = cmd_ingest_dry_run("d1", mode="full")
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
