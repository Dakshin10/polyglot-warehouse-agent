"""SQLite source connector for Cloudflare D1 and local development databases."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Generator, Optional
import pandas as pd

from pwa.ingestion.connectors.base import (
    BatchResult,
    SchemaColumn,
    SourceConnector,
    TableSchema,
)

logger = logging.getLogger("pwa.connectors.sqlite")


class SQLiteConnector(SourceConnector):
    """Connector adapter for Cloudflare D1 (SQLite) and local SQLite database files."""

    def __init__(self, source_name: str, connection_config: dict[str, Any] | str) -> None:
        if isinstance(connection_config, str):
            connection_config = {"local_path": connection_config}
        super().__init__(source_name, connection_config)
        self.db_path = Path(connection_config.get("db_path", connection_config.get("local_path", "")))
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        if not self.db_path.exists():
            raise FileNotFoundError(f"SQLite database file not found: {self.db_path}")
        self._conn = sqlite3.connect(self.db_path)
        self.is_connected = True

    def test_connection(self) -> bool:
        try:
            if not self.is_connected or self._conn is None:
                self.connect()
            assert self._conn is not None, "connect() did not establish a SQLite connection"
            cur = self._conn.cursor()
            cur.execute("SELECT 1;")
            return cur.fetchone() == (1,)
        except Exception as e:
            logger.warning(f"SQLite test connection failed for {self.source_name}: {e}")
            return False

    def discover_tables(self) -> list[str]:
        if not self.is_connected or self._conn is None:
            self.connect()
        assert self._conn is not None, "connect() did not establish a SQLite connection"
        cur = self._conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        return [r[0] for r in cur.fetchall()]

    def discover_schema(self, table_name: str) -> TableSchema:
        if not self.is_connected or self._conn is None:
            self.connect()
        assert self._conn is not None, "connect() did not establish a SQLite connection"
        cur = self._conn.cursor()
        cur.execute(
            f"PRAGMA table_info('{table_name}');"
        )  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        cols = []
        pk_cols = []
        for r in cur.fetchall():
            col_name = r[1]
            data_type = r[2] or "TEXT"
            not_null = bool(r[3])
            is_pk = bool(r[5])
            cols.append(SchemaColumn(name=col_name, data_type=data_type, nullable=not not_null, is_pk=is_pk))
            if is_pk:
                pk_cols.append(col_name)

        return TableSchema(table_name=table_name, columns=cols, primary_key=pk_cols)

    def has_update_trigger(self, table_name: str, watermark_col: str) -> bool:
        """Check if an AFTER UPDATE trigger exists on SQLite table setting watermark_col."""
        if not self.is_connected or self._conn is None:
            self.connect()
        assert self._conn is not None, "connect() did not establish a SQLite connection"
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name=? AND sql LIKE '%UPDATE%' AND sql LIKE ?;",
                (table_name, f"%{watermark_col}%"),
            )
            return cur.fetchone() is not None
        except Exception:
            return False

    def extract(
        self,
        table_name: str,
        batch_size: int = 5000,
        watermark_col: Optional[str] = None,
        watermark_val: Optional[Any] = None,
    ) -> Generator[BatchResult, None, None]:
        if not self.is_connected or self._conn is None:
            self.connect()
        assert self._conn is not None, "connect() did not establish a SQLite connection"

        query = f"SELECT * FROM {table_name}"
        params = []
        if watermark_col and watermark_val is not None:
            if self.has_update_trigger(table_name, watermark_col):
                query += f" WHERE {watermark_col} > ?"
                params.append(str(watermark_val))
            else:
                logger.warning(
                    f"[{self.source_name}] Table `{table_name}` has watermark_col='{watermark_col}' "
                    "without a verified AFTER UPDATE trigger in SQLite/D1. Falling back to full-table extraction "
                    "with payload hash change detection (_pwa_payload_hash)."
                )

        cur = self._conn.cursor()
        cur.execute(
            query, params
        )  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query

        col_names = [d[0] for d in cur.description] if cur.description else []
        batch_idx = 0

        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break
            df = pd.DataFrame(rows, columns=col_names)
            has_more = len(rows) == batch_size
            yield BatchResult(
                table_name=table_name,
                df=df,
                record_count=len(df),
                batch_index=batch_idx,
                has_more=has_more,
            )
            batch_idx += 1

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        self.is_connected = False
