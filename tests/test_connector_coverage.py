"""Targeted unit tests to cover uncovered lines in connector modules.

Executes 100% offline — all DB clients (psycopg2, mysql.connector, sqlite3)
are mocked.  No live cloud or local-file access required.
"""

from __future__ import annotations

import sqlite3
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Generator
from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd
import pytest

from pwa.ingestion.connectors.base import (
    BatchResult,
    SchemaColumn,
    TableSchema,
    SourceConnector,
    get_connector_for_source,
)
from pwa.ingestion.connectors.sqlite_connector import SQLiteConnector
from pwa.ingestion.connectors.postgres_connector import PostgreSQLConnector
from pwa.ingestion.connectors.mysql_connector import MySQLConnector
from pwa.ingestion.extractor import TableExtractor, compute_effective_watermark


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / shared fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def tmp_sqlite_db(tmp_path: Path) -> Path:
    """Create a minimal SQLite DB with a test table and an update trigger."""
    db_file = tmp_path / "test.sqlite"
    con = sqlite3.connect(db_file)
    con.execute(
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, name TEXT, updated_at TEXT)"
    )
    con.execute(
        "INSERT INTO orders VALUES (1, 'Widget', '2026-01-01T00:00:00')"
    )
    con.execute(
        "INSERT INTO orders VALUES (2, 'Gadget', '2026-06-01T00:00:00')"
    )
    # Add a proper AFTER UPDATE trigger so has_update_trigger() returns True
    con.execute(
        """
        CREATE TRIGGER trg_orders_updated_at
        AFTER UPDATE ON orders
        BEGIN
            UPDATE orders SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
        """
    )
    con.commit()
    con.close()
    return db_file


# ═══════════════════════════════════════════════════════════════════════════════
# base.py
# ═══════════════════════════════════════════════════════════════════════════════

class TestTableSchema:
    """Covers lines 30-33 — TableSchema.get_column()."""

    def test_get_column_found_case_insensitive(self):
        schema = TableSchema(
            table_name="users",
            columns=[SchemaColumn("UserID", "integer", is_pk=True), SchemaColumn("email", "text")],
        )
        col = schema.get_column("userid")
        assert col is not None
        assert col.name == "UserID"

    def test_get_column_missing_returns_none(self):
        schema = TableSchema(table_name="users", columns=[SchemaColumn("id", "integer")])
        assert schema.get_column("nonexistent") is None


class TestSourceConnectorContextManager:
    """Covers lines 91-96 — __enter__ / __exit__."""

    def test_context_manager_calls_connect_and_close(self, tmp_sqlite_db: Path):
        connector = SQLiteConnector("ctx_test", {"local_path": str(tmp_sqlite_db)})
        with connector as c:
            assert c.is_connected is True
        assert connector.is_connected is False
        assert connector._conn is None


class TestGetConnectorFactory:
    """Covers lines 101-120 — get_connector_for_source() factory."""

    def _src(self, **kwargs):
        return SimpleNamespace(**kwargs)

    def test_postgres_by_db_type(self):
        src = self._src(name="alloydb_src", db_type="postgres", local_path=None, config={})
        connector = get_connector_for_source(src)
        assert isinstance(connector, PostgreSQLConnector)

    def test_alloy_by_name(self):
        src = self._src(name="alloydb_prod", db_type="", local_path=None, config={})
        connector = get_connector_for_source(src)
        assert isinstance(connector, PostgreSQLConnector)

    def test_mysql_by_db_type(self):
        src = self._src(name="src", db_type="mysql", local_path=None, config={})
        connector = get_connector_for_source(src)
        assert isinstance(connector, MySQLConnector)

    def test_aiven_by_name(self):
        src = self._src(name="aiven_mysql", db_type="", local_path=None, config={})
        connector = get_connector_for_source(src)
        assert isinstance(connector, MySQLConnector)

    def test_sqlite_fallback(self):
        src = self._src(name="d1_source", db_type="sqlite", local_path=None, config={})
        connector = get_connector_for_source(src)
        assert isinstance(connector, SQLiteConnector)

    def test_db_path_from_config_dict(self):
        src = self._src(name="d1_source", db_type="sqlite", local_path=None,
                        config={"local_path": "data/db/d1/some.sqlite"})
        connector = get_connector_for_source(src)
        assert isinstance(connector, SQLiteConnector)


# ═══════════════════════════════════════════════════════════════════════════════
# sqlite_connector.py
# ═══════════════════════════════════════════════════════════════════════════════

class TestSQLiteConnectorConnect:
    """Covers lines 26, 33 — connect() + string config shorthand."""

    def test_string_config_accepted(self, tmp_sqlite_db: Path):
        # line 25-26: string → dict coercion path
        connector = SQLiteConnector("str_cfg", str(tmp_sqlite_db))
        connector.connect()
        assert connector.is_connected is True
        connector.close()

    def test_connect_missing_file_raises(self, tmp_path: Path):
        # line 33: FileNotFoundError branch
        connector = SQLiteConnector("missing", {"local_path": str(tmp_path / "ghost.sqlite")})
        with pytest.raises(FileNotFoundError, match="not found"):
            connector.connect()


class TestSQLiteConnectorTestConnection:
    """Covers lines 38-47 — test_connection()."""

    def test_test_connection_success(self, tmp_sqlite_db: Path):
        connector = SQLiteConnector("tc", {"local_path": str(tmp_sqlite_db)})
        assert connector.test_connection() is True
        connector.close()

    def test_test_connection_auto_connects(self, tmp_sqlite_db: Path):
        # Calls connect() lazily when not yet connected
        connector = SQLiteConnector("tc_lazy", {"local_path": str(tmp_sqlite_db)})
        assert connector.is_connected is False
        assert connector.test_connection() is True
        connector.close()

    def test_test_connection_returns_false_on_exception(self, tmp_sqlite_db: Path):
        connector = SQLiteConnector("tc_err", {"local_path": str(tmp_sqlite_db)})
        connector.connect()
        # Break the connection object to force exception
        connector._conn = MagicMock()
        connector._conn.cursor.side_effect = Exception("boom")
        result = connector.test_connection()
        assert result is False


class TestSQLiteConnectorDiscoverTables:
    """Covers lines 50-55 — discover_tables()."""

    def test_discover_tables_returns_list(self, tmp_sqlite_db: Path):
        connector = SQLiteConnector("dt", {"local_path": str(tmp_sqlite_db)})
        tables = connector.discover_tables()
        assert "orders" in tables
        connector.close()

    def test_discover_tables_auto_connects(self, tmp_sqlite_db: Path):
        connector = SQLiteConnector("dt_lazy", {"local_path": str(tmp_sqlite_db)})
        assert connector.is_connected is False
        tables = connector.discover_tables()
        assert isinstance(tables, list)
        connector.close()


class TestSQLiteConnectorDiscoverSchema:
    """Covers lines 58-74 — discover_schema()."""

    def test_discover_schema_columns_and_pk(self, tmp_sqlite_db: Path):
        connector = SQLiteConnector("ds", {"local_path": str(tmp_sqlite_db)})
        schema = connector.discover_schema("orders")
        assert schema.table_name == "orders"
        col_names = [c.name for c in schema.columns]
        assert "id" in col_names
        assert "name" in col_names
        # PK detected
        assert "id" in schema.primary_key
        connector.close()

    def test_discover_schema_auto_connects(self, tmp_sqlite_db: Path):
        connector = SQLiteConnector("ds_lazy", {"local_path": str(tmp_sqlite_db)})
        assert connector.is_connected is False
        schema = connector.discover_schema("orders")
        assert len(schema.columns) > 0
        connector.close()


class TestSQLiteConnectorHasUpdateTrigger:
    """Covers lines 79, 88-89 — has_update_trigger() connect-lazy + except branch."""

    def test_trigger_detected(self, tmp_sqlite_db: Path):
        connector = SQLiteConnector("trig", {"local_path": str(tmp_sqlite_db)})
        assert connector.is_connected is False  # lazy connect test
        result = connector.has_update_trigger("orders", "updated_at")
        assert result is True
        connector.close()

    def test_trigger_missing_returns_false(self, tmp_sqlite_db: Path):
        connector = SQLiteConnector("trig_miss", {"local_path": str(tmp_sqlite_db)})
        result = connector.has_update_trigger("orders", "nonexistent_col")
        assert result is False
        connector.close()

    def test_trigger_exception_returns_false(self, tmp_sqlite_db: Path):
        connector = SQLiteConnector("trig_ex", {"local_path": str(tmp_sqlite_db)})
        connector.connect()
        connector._conn = MagicMock()
        connector._conn.cursor.side_effect = Exception("db error")
        assert connector.has_update_trigger("orders", "updated_at") is False


class TestSQLiteExtractWatermarkBranch:
    """Covers lines 106-107 — watermark WHERE clause + fallback warning."""

    def test_extract_with_verified_trigger_applies_where(self, tmp_sqlite_db: Path):
        connector = SQLiteConnector("wm", {"local_path": str(tmp_sqlite_db)})
        # updated_at trigger exists — WHERE clause should be applied
        batches = list(
            connector.extract("orders", batch_size=100,
                              watermark_col="updated_at",
                              watermark_val="2026-03-01T00:00:00")
        )
        # Only the 2026-06-01 row should be returned
        assert len(batches) == 1
        assert len(batches[0].df) == 1
        assert batches[0].df.iloc[0]["name"] == "Gadget"
        connector.close()

    def test_extract_without_trigger_falls_back_to_full_scan(self, tmp_sqlite_db: Path, caplog):
        import logging
        connector = SQLiteConnector("wm_fb", {"local_path": str(tmp_sqlite_db)})
        with caplog.at_level(logging.WARNING, logger="pwa.connectors.sqlite"):
            batches = list(
                connector.extract("orders", batch_size=100,
                                  watermark_col="nonexistent_wm",
                                  watermark_val="2026-03-01T00:00:00")
            )
        # Full scan — both rows returned
        total_rows = sum(len(b.df) for b in batches)
        assert total_rows == 2
        assert "Falling back to full-table extraction" in caplog.text
        connector.close()

    def test_extract_no_watermark_returns_all(self, tmp_sqlite_db: Path):
        connector = SQLiteConnector("wm_none", {"local_path": str(tmp_sqlite_db)})
        batches = list(connector.extract("orders", batch_size=100))
        assert sum(len(b.df) for b in batches) == 2
        connector.close()

    def test_extract_batch_pagination(self, tmp_sqlite_db: Path):
        """Verify multi-batch iteration when batch_size=1 yields 2 batches."""
        connector = SQLiteConnector("pag", {"local_path": str(tmp_sqlite_db)})
        batches = list(connector.extract("orders", batch_size=1))
        # 2 rows → 2 batches when batch_size=1
        assert len(batches) == 2
        assert batches[0].batch_index == 0
        assert batches[1].batch_index == 1
        # has_more is True on both because fetchmany can't look ahead (len==batch_size)
        assert batches[0].has_more is True
        connector.close()


# ═══════════════════════════════════════════════════════════════════════════════
# postgres_connector.py  — mocked psycopg2 (no live PG needed)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPostgreSQLConnectorFallback:
    """Covers lines 56-60 — fallback connect() path when credentials missing."""

    def test_connects_via_fallback_when_no_creds(self, tmp_sqlite_db: Path):
        connector = PostgreSQLConnector("pg_fallback", {"local_path": str(tmp_sqlite_db)})
        # No host/user/database → _should_use_fallback() is True
        connector.connect()
        assert connector.is_connected is True
        assert connector._fallback_connector is not None
        connector.close()

    def test_fallback_test_connection(self, tmp_sqlite_db: Path):
        connector = PostgreSQLConnector("pg_tc", {"local_path": str(tmp_sqlite_db)})
        connector.connect()
        assert connector.test_connection() is True
        connector.close()

    def test_fallback_discover_tables(self, tmp_sqlite_db: Path):
        connector = PostgreSQLConnector("pg_dt", {"local_path": str(tmp_sqlite_db)})
        connector.connect()
        tables = connector.discover_tables()
        assert "orders" in tables
        connector.close()

    def test_fallback_discover_schema(self, tmp_sqlite_db: Path):
        connector = PostgreSQLConnector("pg_ds", {"local_path": str(tmp_sqlite_db)})
        connector.connect()
        schema = connector.discover_schema("orders")
        assert schema.table_name == "orders"
        connector.close()

    def test_fallback_extract(self, tmp_sqlite_db: Path):
        connector = PostgreSQLConnector("pg_ex", {"local_path": str(tmp_sqlite_db)})
        connector.connect()
        batches = list(connector.extract("orders", batch_size=100))
        assert sum(len(b.df) for b in batches) == 2
        connector.close()

    def test_fallback_close_clears_state(self, tmp_sqlite_db: Path):
        connector = PostgreSQLConnector("pg_close", {"local_path": str(tmp_sqlite_db)})
        connector.connect()
        connector.close()
        assert connector._fallback_connector is None
        assert connector.is_connected is False


class TestPostgreSQLConnectorDirectPsycopg2:
    """Covers lines 73, 76, 88, 91-103, 106-116, 119-138, 147-182, 185-191.
    Uses a fully mocked psycopg2 connection — no real PG required.
    """

    def _make_connected_pg(self) -> tuple[PostgreSQLConnector, MagicMock]:
        """Return a connector already 'connected' via a mocked _pg_conn."""
        connector = PostgreSQLConnector(
            "pg_direct",
            {"host": "fake-host", "port": 5432, "database": "testdb",
             "user": "testuser", "password": "pw"},
        )
        mock_conn = MagicMock()
        connector._pg_conn = mock_conn
        connector.is_connected = True
        return connector, mock_conn

    def test_test_connection_uses_pg_conn(self):
        connector, mock_conn = self._make_connected_pg()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)
        mock_conn.cursor.return_value = mock_cur

        result = connector.test_connection()
        assert result is True
        mock_cur.execute.assert_called_once_with("SELECT 1;")

    def test_test_connection_returns_false_on_exception(self):
        connector, mock_conn = self._make_connected_pg()
        mock_conn.cursor.side_effect = Exception("pg boom")
        assert connector.test_connection() is False

    def test_discover_tables_direct(self):
        connector, mock_conn = self._make_connected_pg()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [("customers",), ("orders",)]
        mock_conn.cursor.return_value = mock_cur

        tables = connector.discover_tables()
        assert "customers" in tables
        assert "orders" in tables

    def test_discover_schema_direct(self):
        connector, mock_conn = self._make_connected_pg()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("id", "integer", "NO"),
            ("email", "text", "YES"),
        ]
        mock_conn.cursor.return_value = mock_cur

        schema = connector.discover_schema("customers")
        assert schema.table_name == "customers"
        assert len(schema.columns) == 2
        id_col = next(c for c in schema.columns if c.name == "id")
        assert id_col.nullable is False

    def test_extract_direct_no_watermark(self):
        connector, mock_conn = self._make_connected_pg()
        mock_cur = MagicMock()
        mock_cur.description = [("id",), ("email",)]
        mock_cur.fetchmany.side_effect = [
            [(1, "a@b.com"), (2, "c@d.com")],
            [],  # end of results
        ]
        mock_conn.cursor.return_value = mock_cur

        batches = list(connector.extract("customers", batch_size=100))
        assert len(batches) == 1
        assert len(batches[0].df) == 2

    def test_extract_direct_with_watermark(self):
        connector, mock_conn = self._make_connected_pg()
        mock_cur = MagicMock()
        mock_cur.description = [("id",), ("updated_at",)]
        mock_cur.fetchmany.side_effect = [[(3, "2026-09-01")], []]
        mock_conn.cursor.return_value = mock_cur

        batches = list(
            connector.extract("customers", batch_size=100,
                              watermark_col="updated_at",
                              watermark_val="2026-08-01")
        )
        # Watermark param was passed
        call_args = mock_cur.execute.call_args
        assert "WHERE updated_at > %s" in call_args[0][0]
        assert len(batches) == 1

    def test_extract_direct_multi_batch(self):
        """Verify batch_index increments and has_more flag."""
        connector, mock_conn = self._make_connected_pg()
        mock_cur = MagicMock()
        mock_cur.description = [("id",)]
        mock_cur.fetchmany.side_effect = [
            [(i,) for i in range(2)],  # batch 0, batch_size=2 → has_more=True
            [(i,) for i in range(2)],  # batch 1, batch_size=2 → has_more=True
            [],
        ]
        mock_conn.cursor.return_value = mock_cur

        batches = list(connector.extract("t", batch_size=2))
        assert len(batches) == 2
        assert batches[0].batch_index == 0
        assert batches[0].has_more is True
        assert batches[1].batch_index == 1

    def test_close_clears_pg_conn(self):
        connector, mock_conn = self._make_connected_pg()
        connector.close()
        mock_conn.close.assert_called_once()
        assert connector._pg_conn is None
        assert connector.is_connected is False

    def test_connect_raises_in_production_without_creds(self):
        """line 52-55: Production mode + missing creds must raise."""
        from pwa.settings import ProductionEnvironmentError

        connector = PostgreSQLConnector("pg_prod", {"local_path": "/nonexistent.sqlite"})
        with patch("pwa.settings.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.is_production = True
            mock_gs.return_value = mock_settings
            with pytest.raises(ProductionEnvironmentError):
                connector.connect()

    def test_connect_psycopg2_success_sets_is_connected(self):
        """Line 73: psycopg2 connect success path."""
        connector = PostgreSQLConnector(
            "pg_succ",
            {"host": "valid-host", "port": 5432, "database": "db", "user": "u", "password": "p"}
        )
        mock_psycopg2 = MagicMock()
        mock_conn = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            connector.connect()

        assert connector.is_connected is True
        assert connector._pg_conn == mock_conn

    def test_connect_psycopg2_failure_in_production_raises(self):
        """Line 76: psycopg2 connect fails in production mode."""
        from pwa.settings import ProductionEnvironmentError

        connector = PostgreSQLConnector(
            "pg_prod_fail",
            {"host": "valid-host", "port": 5432, "database": "db", "user": "u", "password": "p"}
        )
        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.side_effect = Exception("connection failed")

        with patch("pwa.settings.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.is_production = True
            mock_gs.return_value = mock_settings
            with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
                with pytest.raises(ProductionEnvironmentError, match="PostgreSQL connection to valid-host:5432 failed"):
                    connector.connect()

    def test_connect_psycopg2_failure_missing_fallback_file_raises(self):
        """Line 88: psycopg2 connect fails in dev mode with non-existent fallback file."""
        connector = PostgreSQLConnector(
            "pg_no_fb",
            {"host": "valid-host", "port": 5432, "database": "db", "user": "u", "password": "p", "local_path": "/nonexistent/path/db.sqlite"}
        )
        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.side_effect = Exception("conn failed")

        with patch("pwa.settings.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.is_production = False
            mock_gs.return_value = mock_settings
            with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
                with pytest.raises(Exception, match="conn failed"):
                    connector.connect()

    def test_connect_falls_back_on_psycopg2_failure(self, tmp_sqlite_db: Path):
        """lines 80-86: psycopg2 import OK but connect() raises → SQLite fallback."""
        connector = PostgreSQLConnector(
            "pg_retry",
            {"host": "bad-host", "port": 5432, "database": "db",
             "user": "u", "password": "p",
             "local_path": str(tmp_sqlite_db)},
        )

        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.side_effect = Exception("connection refused")

        with patch("pwa.settings.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.is_production = False
            mock_gs.return_value = mock_settings
            with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
                connector.connect()

        assert connector.is_connected is True
        assert connector._fallback_connector is not None
        connector.close()

    def test_lazy_auto_connect_fallback_delegation(self, tmp_sqlite_db: Path):
        """Covers lines 94, 96, 109, 111, 122, 124, 152, 155-156: calling connector methods when NOT connected."""
        connector = PostgreSQLConnector("pg_unconnected", {"local_path": str(tmp_sqlite_db)})
        assert connector.is_connected is False

        # test_connection() on unconnected connector -> calls connect() (line 94) -> delegates to fallback (line 96)
        assert connector.test_connection() is True
        connector.close()

        connector2 = PostgreSQLConnector("pg_unconnected2", {"local_path": str(tmp_sqlite_db)})
        # discover_tables() on unconnected connector -> calls connect() (line 109) -> delegates to fallback (line 111)
        tables = connector2.discover_tables()
        assert "orders" in tables
        connector2.close()

        connector3 = PostgreSQLConnector("pg_unconnected3", {"local_path": str(tmp_sqlite_db)})
        # discover_schema() on unconnected connector -> calls connect() (line 122) -> delegates to fallback (line 124)
        schema = connector3.discover_schema("orders")
        assert schema.table_name == "orders"
        connector3.close()

        connector4 = PostgreSQLConnector("pg_unconnected4", {"local_path": str(tmp_sqlite_db)})
        # extract() on unconnected connector -> calls connect() (line 152) -> delegates to fallback (lines 155-156)
        batches = list(connector4.extract("orders", batch_size=100))
        assert sum(len(b.df) for b in batches) == 2
        connector4.close()


# ═══════════════════════════════════════════════════════════════════════════════
# mysql_connector.py — mocked mysql.connector
# ═══════════════════════════════════════════════════════════════════════════════

class TestMySQLConnectorFallback:
    """Covers lines 56-86 — fallback connect() path when credentials missing."""

    def test_connects_via_fallback_when_no_creds(self, tmp_sqlite_db: Path):
        connector = MySQLConnector("mysql_fb", {"local_path": str(tmp_sqlite_db)})
        connector.connect()
        assert connector.is_connected is True
        assert connector._fallback_connector is not None
        connector.close()

    def test_fallback_test_connection(self, tmp_sqlite_db: Path):
        connector = MySQLConnector("mysql_tc", {"local_path": str(tmp_sqlite_db)})
        connector.connect()
        assert connector.test_connection() is True
        connector.close()

    def test_fallback_discover_tables(self, tmp_sqlite_db: Path):
        connector = MySQLConnector("mysql_dt", {"local_path": str(tmp_sqlite_db)})
        connector.connect()
        tables = connector.discover_tables()
        assert "orders" in tables
        connector.close()

    def test_fallback_discover_schema(self, tmp_sqlite_db: Path):
        connector = MySQLConnector("mysql_ds", {"local_path": str(tmp_sqlite_db)})
        connector.connect()
        schema = connector.discover_schema("orders")
        assert schema.table_name == "orders"
        connector.close()

    def test_fallback_extract(self, tmp_sqlite_db: Path):
        connector = MySQLConnector("mysql_ex", {"local_path": str(tmp_sqlite_db)})
        connector.connect()
        batches = list(connector.extract("orders", batch_size=100))
        assert sum(len(b.df) for b in batches) == 2
        connector.close()

    def test_fallback_close_clears_state(self, tmp_sqlite_db: Path):
        connector = MySQLConnector("mysql_cl", {"local_path": str(tmp_sqlite_db)})
        connector.connect()
        connector.close()
        assert connector._fallback_connector is None
        assert connector.is_connected is False


class TestMySQLConnectorDirectClient:
    """Covers lines 89-101, 104-114, 117-138, 147-182, 185-191.
    Uses a fully mocked mysql.connector — no real MySQL required.
    """

    def _make_connected_mysql(self) -> tuple[MySQLConnector, MagicMock]:
        connector = MySQLConnector(
            "mysql_direct",
            {"host": "fake-host", "port": 3306, "database": "testdb",
             "user": "testuser", "password": "pw"},
        )
        mock_conn = MagicMock()
        connector._mysql_conn = mock_conn
        connector.is_connected = True
        return connector, mock_conn

    def test_test_connection_uses_mysql_conn(self):
        connector, mock_conn = self._make_connected_mysql()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)
        mock_conn.cursor.return_value = mock_cur

        assert connector.test_connection() is True
        mock_cur.execute.assert_called_once_with("SELECT 1;")

    def test_test_connection_returns_false_on_exception(self):
        connector, mock_conn = self._make_connected_mysql()
        mock_conn.cursor.side_effect = Exception("mysql boom")
        assert connector.test_connection() is False

    def test_discover_tables_direct(self):
        connector, mock_conn = self._make_connected_mysql()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [("customers",), ("suppliers",)]
        mock_conn.cursor.return_value = mock_cur

        tables = connector.discover_tables()
        assert "customers" in tables
        mock_cur.execute.assert_called_once_with("SHOW TABLES;")

    def test_discover_schema_direct(self):
        connector, mock_conn = self._make_connected_mysql()
        mock_cur = MagicMock()
        # DESCRIBE cols: (name, type, nullable, key, default, extra)
        mock_cur.fetchall.return_value = [
            ("id", "int", "NO", "PRI", None, ""),
            ("email", "varchar(255)", "YES", "", None, ""),
        ]
        mock_conn.cursor.return_value = mock_cur

        schema = connector.discover_schema("customers")
        assert schema.table_name == "customers"
        assert "id" in schema.primary_key
        id_col = next(c for c in schema.columns if c.name == "id")
        assert id_col.is_pk is True

    def test_extract_direct_no_watermark(self):
        connector, mock_conn = self._make_connected_mysql()
        mock_cur = MagicMock()
        mock_cur.description = [("id",), ("email",)]
        mock_cur.fetchmany.side_effect = [[(1, "a@b.com")], []]
        mock_conn.cursor.return_value = mock_cur

        batches = list(connector.extract("customers", batch_size=100))
        assert len(batches) == 1
        assert len(batches[0].df) == 1

    def test_extract_direct_with_watermark(self):
        connector, mock_conn = self._make_connected_mysql()
        mock_cur = MagicMock()
        mock_cur.description = [("id",), ("updated_at",)]
        mock_cur.fetchmany.side_effect = [[(5, "2026-09-01")], []]
        mock_conn.cursor.return_value = mock_cur

        batches = list(
            connector.extract("customers", batch_size=100,
                              watermark_col="updated_at",
                              watermark_val="2026-08-01")
        )
        call_args = mock_cur.execute.call_args
        assert "WHERE updated_at > %s" in call_args[0][0]
        assert len(batches) == 1

    def test_extract_multi_batch_has_more(self):
        connector, mock_conn = self._make_connected_mysql()
        mock_cur = MagicMock()
        mock_cur.description = [("id",)]
        mock_cur.fetchmany.side_effect = [[(1,), (2,)], [(3,), (4,)], []]
        mock_conn.cursor.return_value = mock_cur

        batches = list(connector.extract("t", batch_size=2))
        assert len(batches) == 2
        assert batches[0].has_more is True

    def test_close_clears_mysql_conn(self):
        connector, mock_conn = self._make_connected_mysql()
        connector.close()
        mock_conn.close.assert_called_once()
        assert connector._mysql_conn is None
        assert connector.is_connected is False

    def test_connect_raises_in_production_without_creds(self):
        from pwa.settings import ProductionEnvironmentError

        connector = MySQLConnector("mysql_prod", {"local_path": "/nonexistent.sqlite"})
        with patch("pwa.settings.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.is_production = True
            mock_gs.return_value = mock_settings
            with pytest.raises(ProductionEnvironmentError):
                connector.connect()

    def test_connect_mysql_success_sets_is_connected(self):
        """Line 73: mysql.connector connect success path."""
        connector = MySQLConnector(
            "mysql_succ",
            {"host": "valid-host", "port": 3306, "database": "db", "user": "u", "password": "p"}
        )
        mock_mysql_mod = MagicMock()
        mock_conn = MagicMock()
        mock_mysql_mod.connector.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"mysql": mock_mysql_mod, "mysql.connector": mock_mysql_mod.connector}):
            connector.connect()

        assert connector.is_connected is True
        assert connector._mysql_conn == mock_conn

    def test_connect_mysql_failure_in_production_raises(self):
        """Line 76: mysql.connector connect fails in production mode."""
        from pwa.settings import ProductionEnvironmentError

        connector = MySQLConnector(
            "mysql_prod_fail",
            {"host": "valid-host", "port": 3306, "database": "db", "user": "u", "password": "p"}
        )
        mock_mysql_mod = MagicMock()
        mock_mysql_mod.connector.connect.side_effect = Exception("mysql connection failed")

        with patch("pwa.settings.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.is_production = True
            mock_gs.return_value = mock_settings
            with patch.dict("sys.modules", {"mysql": mock_mysql_mod, "mysql.connector": mock_mysql_mod.connector}):
                with pytest.raises(ProductionEnvironmentError, match="MySQL connection to valid-host:3306 failed"):
                    connector.connect()

    def test_connect_mysql_failure_missing_fallback_file_raises(self):
        """Line 86: mysql.connector connect fails in dev mode with non-existent fallback file."""
        connector = MySQLConnector(
            "mysql_no_fb",
            {"host": "valid-host", "port": 3306, "database": "db", "user": "u", "password": "p", "local_path": "/nonexistent/path/db.sqlite"}
        )
        mock_mysql_mod = MagicMock()
        mock_mysql_mod.connector.connect.side_effect = Exception("mysql conn failed")

        with patch("pwa.settings.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.is_production = False
            mock_gs.return_value = mock_settings
            with patch.dict("sys.modules", {"mysql": mock_mysql_mod, "mysql.connector": mock_mysql_mod.connector}):
                with pytest.raises(Exception, match="mysql conn failed"):
                    connector.connect()

    def test_connect_falls_back_on_mysql_failure(self, tmp_sqlite_db: Path):
        """Lines 80-84: mysql.connector raises → SQLite fallback."""
        connector = MySQLConnector(
            "mysql_retry",
            {"host": "bad-host", "port": 3306, "database": "db",
             "user": "u", "password": "p",
             "local_path": str(tmp_sqlite_db)},
        )

        mock_mysql_mod = MagicMock()
        mock_mysql_mod.connector = MagicMock()
        mock_mysql_mod.connector.connect.side_effect = Exception("connection refused")

        with patch("pwa.settings.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.is_production = False
            mock_gs.return_value = mock_settings
            with patch.dict("sys.modules", {"mysql": mock_mysql_mod,
                                            "mysql.connector": mock_mysql_mod.connector}):
                connector.connect()

        assert connector.is_connected is True
        assert connector._fallback_connector is not None
        connector.close()

    def test_mysql_lazy_auto_connect_fallback_delegation(self, tmp_sqlite_db: Path):
        """Covers lines 94, 96, 109, 111, 122, 124, 152, 155-156: calling connector methods when NOT connected."""
        connector = MySQLConnector("mysql_unconnected", {"local_path": str(tmp_sqlite_db)})
        assert connector.is_connected is False

        assert connector.test_connection() is True
        connector.close()

        connector2 = MySQLConnector("mysql_unconnected2", {"local_path": str(tmp_sqlite_db)})
        tables = connector2.discover_tables()
        assert "orders" in tables
        connector2.close()

        connector3 = MySQLConnector("mysql_unconnected3", {"local_path": str(tmp_sqlite_db)})
        schema = connector3.discover_schema("orders")
        assert schema.table_name == "orders"
        connector3.close()

        connector4 = MySQLConnector("mysql_unconnected4", {"local_path": str(tmp_sqlite_db)})
        batches = list(connector4.extract("orders", batch_size=100))
        assert sum(len(b.df) for b in batches) == 2
        connector4.close()


# ═══════════════════════════════════════════════════════════════════════════════
# extractor.py  — compute_effective_watermark + TableExtractor
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeEffectiveWatermark:
    """Covers lines 22, 27-28, 35."""

    def test_none_watermark_returns_none(self):
        # line 22: None path
        assert compute_effective_watermark(None) is None

    def test_empty_string_returns_none(self):
        # line 22: empty string path
        assert compute_effective_watermark("") is None

    def test_valid_datetime_applies_lookback(self):
        # line 24-26: happy path
        result = compute_effective_watermark("2026-09-01T10:00:00", lookback_minutes=30)
        assert result is not None
        assert "2026-09-01T09:30:00" in result

    def test_non_parseable_returns_original(self):
        # line 27-28: exception fallback returns original value
        result = compute_effective_watermark("not-a-date", lookback_minutes=5)
        assert result == "not-a-date"


class TestTableExtractor:
    """Covers lines 47-92 — extract_table() main logic."""

    def _make_mock_connector(self, batches: list[pd.DataFrame]) -> MagicMock:
        connector = MagicMock()
        connector.source_name = "mock_source"

        def _extract(**kwargs):
            for idx, df in enumerate(batches):
                yield BatchResult(
                    table_name=kwargs.get("table_name", "t"),
                    df=df,
                    record_count=len(df),
                    batch_index=idx,
                    has_more=(idx < len(batches) - 1),
                )

        connector.extract.side_effect = _extract
        return connector

    def test_extract_table_yields_metadata_dict(self, tmp_sqlite_db: Path):
        df1 = pd.DataFrame({"id": [1, 2], "val": ["a", "b"]})
        connector = self._make_mock_connector([df1])
        extractor = TableExtractor(connector)

        results = list(extractor.extract_table("orders", run_id="run-xyz"))
        assert len(results) == 1
        r = results[0]
        assert r["run_id"] == "run-xyz"
        assert r["source_system"] == "mock_source"
        assert r["table_name"] == "orders"
        assert r["record_count"] == 2
        assert r["batch_index"] == 0
        assert "df" in r

    def test_extract_table_auto_generates_run_id(self):
        df1 = pd.DataFrame({"id": [10]})
        connector = self._make_mock_connector([df1])
        extractor = TableExtractor(connector)

        results = list(extractor.extract_table("t"))
        assert len(results) == 1
        # run_id should be a valid UUID string
        assert uuid.UUID(results[0]["run_id"])

    def test_extract_table_skips_empty_batches(self):
        empty_df = pd.DataFrame()
        full_df = pd.DataFrame({"id": [1]})
        connector = self._make_mock_connector([empty_df, full_df])
        extractor = TableExtractor(connector)

        results = list(extractor.extract_table("t"))
        assert len(results) == 1  # Empty batch was skipped
        assert results[0]["record_count"] == 1

    def test_extract_table_with_watermark_applies_lookback(self):
        df1 = pd.DataFrame({"id": [1]})
        connector = self._make_mock_connector([df1])
        extractor = TableExtractor(connector)

        list(extractor.extract_table(
            "t",
            watermark_col="updated_at",
            watermark_val="2026-09-01T10:00:00",
            lookback_minutes=60,
        ))

        call_kwargs = connector.extract.call_args[1]
        # effective watermark should be 60 min before 10:00 = 09:00
        assert "2026-09-01T09:00:00" in call_kwargs["watermark_val"]

    def test_extract_table_no_watermark_passes_none(self):
        df1 = pd.DataFrame({"id": [1]})
        connector = self._make_mock_connector([df1])
        extractor = TableExtractor(connector)

        list(extractor.extract_table("t"))
        call_kwargs = connector.extract.call_args[1]
        assert call_kwargs["watermark_val"] is None

    def test_extract_table_multi_batch_has_more_flag(self):
        dfs = [pd.DataFrame({"id": [i]}) for i in range(3)]
        connector = self._make_mock_connector(dfs)
        extractor = TableExtractor(connector)

        results = list(extractor.extract_table("t"))
        assert len(results) == 3
        assert results[0]["has_more"] is True
        assert results[2]["has_more"] is False

    def test_extract_table_provenance_columns_injected(self):
        df1 = pd.DataFrame({"id": [1, 2]})
        connector = self._make_mock_connector([df1])
        extractor = TableExtractor(connector)

        results = list(extractor.extract_table("orders", run_id="prov-test"))
        out_df = results[0]["df"]
        # Provenance metadata columns should be present (from add_provenance_metadata)
        assert "_pwa_run_id" in out_df.columns
        assert "_pwa_source_system" in out_df.columns
        assert "_pwa_source_table" in out_df.columns
        assert "_pwa_payload_hash" in out_df.columns
        assert out_df["_pwa_run_id"].iloc[0] == "prov-test"
        assert out_df["_pwa_source_system"].iloc[0] == "mock_source"
        assert out_df["_pwa_source_table"].iloc[0] == "orders"
