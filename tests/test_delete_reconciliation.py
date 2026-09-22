"""Unit tests for periodic full PK set reconciliation and delete detection (Task 1)."""

import unittest
from unittest.mock import MagicMock, patch
import pytest

from pwa.quality.reconciliation import SourceTargetReconciler, run_full_reconciliation


class TestDeleteReconciliation(unittest.TestCase):
    def setUp(self):
        self.reconciler = SourceTargetReconciler()

    def test_reconcile_full_primary_keys_no_deletions(self):
        """Test full PK reconciliation when source and target PK sets match perfectly."""
        res = self.reconciler.reconcile_full_primary_keys(sources=["adventureworks"])
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreater(res["tables_checked"], 0)
        self.assertEqual(res["deletions_detected"], 0)

    def test_reconcile_full_primary_keys_with_detected_deletions(self):
        """Test detection of deleted PKs when BigQuery contains PKs no longer in source."""
        # Override BigQuery PKs to simulate a deleted PK
        bq_override = {
            "adventureworks.sales_order_header": {"43659", "43660", "999999"}  # 999999 deleted upstream
        }
        with patch("pwa.smart_cache.evaluate_and_invalidate_cache") as mock_cache_purge:
            res = self.reconciler.reconcile_full_primary_keys(
                sources=["adventureworks"], bq_pks_override=bq_override
            )
            self.assertEqual(res["status"], "SUCCESS")
            self.assertGreater(res["deletions_detected"], 0)
            mock_cache_purge.assert_called_once()

    def test_run_full_reconciliation(self):
        """Test entrypoint function run_full_reconciliation."""
        with patch.object(SourceTargetReconciler, "reconcile_full_primary_keys", return_value={"status": "SUCCESS", "tables_checked": 5, "deletions_detected": 0}):
            ok = run_full_reconciliation()
            self.assertTrue(ok)


def test_dagster_reconciliation_asset_wiring():
    """Test Dagster asset definitions if dagster package is installed."""
    dagster = pytest.importorskip("dagster")
    from pwa.orchestration.dagster_defs import defs, periodic_reconciliation

    asset_names = [a.key.to_user_string() for a in defs.assets]
    assert "periodic_reconciliation" in asset_names

    job_names = [j.name for j in defs.jobs]
    assert "reconciliation_job" in job_names

    schedule_names = [s.name for s in defs.schedules]
    assert "daily_reconciliation_schedule" in schedule_names


if __name__ == "__main__":
    unittest.main()
