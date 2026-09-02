import pytest
from sqlalchemy import text
from pwa.db import get_mysql_engine


@pytest.mark.integration
def test_mysql_connection():
    """Integration test verifying live Aiven MySQL connection."""
    engine, engine_type = get_mysql_engine()
    assert engine_type != "sqlite"
    with engine.connect() as conn:
        res = conn.execute(text("SELECT 1;")).scalar()
        assert res == 1
