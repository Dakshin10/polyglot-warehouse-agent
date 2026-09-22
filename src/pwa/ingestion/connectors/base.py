"""Abstract base class for operational database source connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generator, Optional
import pandas as pd


@dataclass
class SchemaColumn:
    """Represents a column in a source table schema."""

    name: str
    data_type: str
    nullable: bool = True
    is_pk: bool = False


@dataclass
class TableSchema:
    """Represents the schema definition of a source table."""

    table_name: str
    columns: list[SchemaColumn] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)

    def get_column(self, name: str) -> Optional[SchemaColumn]:
        for col in self.columns:
            if col.name.lower() == name.lower():
                return col
        return None


@dataclass
class BatchResult:
    """Represents a extracted batch of data from a source table."""

    table_name: str
    df: pd.DataFrame
    record_count: int
    batch_index: int
    has_more: bool = False


class SourceConnector(ABC):
    """Polymorphic source connector interface for SQLite, PostgreSQL, and MySQL."""

    def __init__(self, source_name: str, connection_config: dict[str, Any]) -> None:
        self.source_name = source_name
        self.connection_config = connection_config
        self.is_connected = False

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the source database."""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test whether the connection can be successfully opened and queried."""
        pass

    @abstractmethod
    def discover_tables(self) -> list[str]:
        """Discover available table names in the source database."""
        pass

    @abstractmethod
    def discover_schema(self, table_name: str) -> TableSchema:
        """Discover schema structure for a given table."""
        pass

    @abstractmethod
    def extract(
        self,
        table_name: str,
        batch_size: int = 5000,
        watermark_col: Optional[str] = None,
        watermark_val: Optional[Any] = None,
    ) -> Generator[BatchResult, None, None]:
        """Extract data from a table in bounded batches as a Generator."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the database connection."""
        pass

    def __enter__(self) -> SourceConnector:
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


def get_connector_for_source(src: Any) -> SourceConnector:
    """Factory helper to instantiate appropriate connector for a registered source definition."""
    db_type = getattr(src, "db_type", None) or getattr(src, "provider", "")
    db_path = getattr(src, "local_path", None) or getattr(src, "file_path", None)
    if not db_path and hasattr(src, "config") and isinstance(src.config, dict):
        db_path = src.config.get("local_path") or src.config.get("db_path")

    name_str = str(getattr(src, "name", "")).lower()
    type_str = str(db_type).lower()

    if "postgres" in type_str or "alloy" in name_str:
        from pwa.ingestion.connectors.postgres_connector import PostgreSQLConnector

        return PostgreSQLConnector(src.name, {"local_path": db_path or "data/db/alloydb/nexora_erp.sqlite"})
    elif "mysql" in type_str or "aiven" in name_str:
        from pwa.ingestion.connectors.mysql_connector import MySQLConnector

        return MySQLConnector(src.name, {"local_path": db_path or "data/db/aiven/nexora_ops.sqlite"})
    else:
        from pwa.ingestion.connectors.sqlite_connector import SQLiteConnector

        return SQLiteConnector(src.name, {"local_path": db_path or "data/db/d1/nexora_app.sqlite"})
