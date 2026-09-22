"""MySQL source connector for Aiven MySQL with dev fallback."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Generator, Optional
import pandas as pd

from pwa.ingestion.connectors.base import (
    BatchResult,
    SchemaColumn,
    SourceConnector,
    TableSchema,
)
from pwa.ingestion.connectors.sqlite_connector import SQLiteConnector

logger = logging.getLogger("pwa.connectors.mysql")


class MySQLConnector(SourceConnector):
    """Connector adapter for Aiven MySQL (MySQL engine).

    If production MySQL parameters are not present or unreachable,
    gracefully delegates to local SQLite fallback database representation.
    """

    def __init__(self, source_name: str, connection_config: dict[str, Any]) -> None:
        super().__init__(source_name, connection_config)
        self.host = connection_config.get("host")
        self.port = connection_config.get("port", 3306)
        self.database = connection_config.get("database")
        self.user = connection_config.get("user")
        self.password = connection_config.get("password")

        # Local fallback file if present
        local_path = connection_config.get("local_path", "data/db/aiven/nexora_ops.sqlite")
        self.fallback_path = Path(local_path)
        self._fallback_connector: Optional[SQLiteConnector] = None
        self._mysql_conn = None

    def _should_use_fallback(self) -> bool:
        return not (self.host and self.database and self.user)

    def connect(self) -> None:
        from pwa.settings import ProductionEnvironmentError, get_settings

        settings = get_settings()

        if self._should_use_fallback():
            if settings.is_production:
                raise ProductionEnvironmentError(
                    f"Production mode error: MySQL connection parameters missing for '{self.source_name}' "
                    "and local SQLite fallback is forbidden in production."
                )
            logger.info(f"[{self.source_name}] Using local SQLite adapter fallback ({self.fallback_path})")
            self._fallback_connector = SQLiteConnector(self.source_name, {"db_path": str(self.fallback_path)})
            self._fallback_connector.connect()
            self.is_connected = True
            return

        try:
            import mysql.connector

            self._mysql_conn = mysql.connector.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                connection_timeout=15,
            )
            self.is_connected = True
        except Exception as exc:
            if settings.is_production:
                raise ProductionEnvironmentError(
                    f"Production mode error: MySQL connection to {self.host}:{self.port} failed ({exc}). "
                    "Local SQLite fallback is forbidden in production."
                ) from exc
            logger.warning(f"MySQL connection to {self.host}:{self.port} failed ({exc}). Falling back to local SQLite.")
            if self.fallback_path.exists():
                self._fallback_connector = SQLiteConnector(self.source_name, {"db_path": str(self.fallback_path)})
                self._fallback_connector.connect()
                self.is_connected = True
            else:
                raise

    def test_connection(self) -> bool:
        if self._fallback_connector:
            return self._fallback_connector.test_connection()
        if not self.is_connected or self._mysql_conn is None:
            self.connect()
        if self._fallback_connector:
            return self._fallback_connector.test_connection()
        assert self._mysql_conn is not None, "connect() did not establish a MySQL connection"
        try:
            cur = self._mysql_conn.cursor()
            cur.execute("SELECT 1;")
            return cur.fetchone() == (1,)
        except Exception:
            return False

    def discover_tables(self) -> list[str]:
        if self._fallback_connector:
            return self._fallback_connector.discover_tables()
        if not self.is_connected or self._mysql_conn is None:
            self.connect()
        if self._fallback_connector:
            return self._fallback_connector.discover_tables()

        assert self._mysql_conn is not None, "connect() did not establish a MySQL connection"
        cur = self._mysql_conn.cursor()
        cur.execute("SHOW TABLES;")
        return [r[0] for r in cur.fetchall()]

    def discover_schema(self, table_name: str) -> TableSchema:
        if self._fallback_connector:
            return self._fallback_connector.discover_schema(table_name)
        if not self.is_connected or self._mysql_conn is None:
            self.connect()
        if self._fallback_connector:
            return self._fallback_connector.discover_schema(table_name)

        assert self._mysql_conn is not None, "connect() did not establish a MySQL connection"
        cur = self._mysql_conn.cursor()
        cur.execute(f"DESCRIBE {table_name};")
        cols = []
        pk_cols = []
        for r in cur.fetchall():
            col_name = r[0]
            data_type = r[1]
            nullable = r[2] == "YES"
            is_pk = r[3] == "PRI"
            cols.append(SchemaColumn(name=col_name, data_type=data_type, nullable=nullable, is_pk=is_pk))
            if is_pk:
                pk_cols.append(col_name)

        return TableSchema(table_name=table_name, columns=cols, primary_key=pk_cols)

    def extract(
        self,
        table_name: str,
        batch_size: int = 5000,
        watermark_col: Optional[str] = None,
        watermark_val: Optional[Any] = None,
    ) -> Generator[BatchResult, None, None]:
        if self._fallback_connector:
            yield from self._fallback_connector.extract(table_name, batch_size, watermark_col, watermark_val)
            return

        if not self.is_connected or self._mysql_conn is None:
            self.connect()

        if self._fallback_connector:
            yield from self._fallback_connector.extract(table_name, batch_size, watermark_col, watermark_val)
            return

        assert self._mysql_conn is not None, "connect() did not establish a MySQL connection"
        cur = self._mysql_conn.cursor()
        query = f"SELECT * FROM {table_name}"
        params = []
        if watermark_col and watermark_val is not None:
            query += f" WHERE {watermark_col} > %s"
            params.append(str(watermark_val))

        cur.execute(query, params)
        col_names = [d[0] for d in cur.description] if cur.description else []
        batch_idx = 0

        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break
            df = pd.DataFrame(rows, columns=col_names)
            yield BatchResult(
                table_name=table_name,
                df=df,
                record_count=len(df),
                batch_index=batch_idx,
                has_more=len(rows) == batch_size,
            )
            batch_idx += 1

    def close(self) -> None:
        if self._fallback_connector:
            self._fallback_connector.close()
            self._fallback_connector = None
        if self._mysql_conn:
            self._mysql_conn.close()
            self._mysql_conn = None
        self.is_connected = False
