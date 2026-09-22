"""Source connectors package for PWA.

Provides unified connector abstractions for SQLite (Cloudflare D1),
PostgreSQL (AlloyDB), and MySQL (Aiven MySQL).
"""

from pwa.ingestion.connectors.base import (
    SourceConnector,
    SchemaColumn,
    TableSchema,
    BatchResult,
)
from pwa.ingestion.connectors.sqlite_connector import SQLiteConnector
from pwa.ingestion.connectors.postgres_connector import PostgreSQLConnector
from pwa.ingestion.connectors.mysql_connector import MySQLConnector

__all__ = [
    "SourceConnector",
    "SchemaColumn",
    "TableSchema",
    "BatchResult",
    "SQLiteConnector",
    "PostgreSQLConnector",
    "MySQLConnector",
]
