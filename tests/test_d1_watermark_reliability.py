"""Unit tests for Cloudflare D1 updated_at watermark reliability audit (Task 2)."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from pwa.source_registry import get_registry
from pwa.ingestion.connectors.sqlite_connector import SQLiteConnector


class TestD1WatermarkReliability(unittest.TestCase):
    def test_d1_sources_yaml_watermark_column_audit(self):
        """Test that fails if any D1 table in sources.yaml specifies a watermark_column

        without an AFTER UPDATE trigger provably maintaining it in SQLite.
        """
        registry = get_registry()
        d1_source = registry.get("cloudflare_d1")
        self.assertIsNotNone(d1_source, "cloudflare_d1 source must be present in registry")

        connector = SQLiteConnector(d1_source.name, {"local_path": str(d1_source.local_dir)})

        unmaintained_tables = []
        for tbl in d1_source.tables:
            if tbl.watermark_column:
                # If a watermark_column is configured, it MUST have a verified trigger
                has_trigger = connector.has_update_trigger(tbl.name, tbl.watermark_column)
                if not has_trigger:
                    unmaintained_tables.append(f"{tbl.name} (watermark_column='{tbl.watermark_column}')")

        self.assertEqual(
            len(unmaintained_tables),
            0,
            f"D1 tables in sources.yaml configured with watermark_column without verified AFTER UPDATE triggers: {unmaintained_tables}. "
            "Remove watermark_column or add verified update trigger to prevent silent data freshness bugs.",
        )

    def test_sqlite_connector_falls_back_when_trigger_missing(self):
        """Test that SQLiteConnector falls back to full-table extraction when update trigger is missing."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            conn = sqlite3.connect(tmp_path)
            conn.execute("CREATE TABLE orders (id INT, updated_at TEXT, item TEXT);")
            conn.execute("INSERT INTO orders VALUES (1, '2026-01-01', 'Widget A');")
            conn.execute("INSERT INTO orders VALUES (2, '2026-01-02', 'Widget B');")
            conn.commit()
            conn.close()

            connector = SQLiteConnector("test_d1", {"local_path": str(tmp_path)})
            batches = list(connector.extract("orders", watermark_col="updated_at", watermark_val="2026-01-01T12:00:00"))

            self.assertEqual(len(batches), 1)
            # Full table extraction fallback must return all 2 rows
            self.assertEqual(len(batches[0].df), 2)
        finally:
            connector.close()
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
