"""Locate and read the DDL / mart SQL files that live in the repository `sql/` directory."""

from pathlib import Path

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def sql_file_path(filename: str) -> Path:
    """Absolute path to a SQL file in the repository `sql/` directory."""
    return SQL_DIR / filename


def read_sql_file(filename: str) -> str:
    """Read a SQL file from the repository `sql/` directory."""
    return sql_file_path(filename).read_text(encoding="utf-8")
