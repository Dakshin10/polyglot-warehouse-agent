import pytest
from sqlalchemy import text
from pwa.db import get_pg_engine


@pytest.mark.integration
def test_postgres_connection():
    """Integration test verifying live Cloud SQL PostgreSQL connection."""
    engine, engine_type = get_pg_engine()
    assert engine_type != "sqlite"
    with engine.connect() as conn:
        res = conn.execute(text("SELECT 1;")).scalar()
        assert res == 1
