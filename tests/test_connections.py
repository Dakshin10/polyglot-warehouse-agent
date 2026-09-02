import pytest
from sqlalchemy import text
from pwa.connections import get_mysql_engine, get_pg_engine, get_bq_client
from pwa.settings import get_settings


@pytest.mark.integration
def test_mysql_connection():
    """Integration test verifying live Aiven MySQL connection."""
    engine, engine_type = get_mysql_engine()
    assert engine_type != "sqlite"
    with engine.connect() as conn:
        res = conn.execute(text("SELECT 1;")).scalar()
        assert res == 1


@pytest.mark.integration
def test_postgres_connection():
    """Integration test verifying live Cloud SQL PostgreSQL connection."""
    engine, engine_type = get_pg_engine()
    assert engine_type != "sqlite"
    with engine.connect() as conn:
        res = conn.execute(text("SELECT 1;")).scalar()
        assert res == 1


@pytest.mark.integration
def test_federation():
    """Integration test verifying BigQuery live EXTERNAL_QUERY connection to Cloud SQL."""
    settings = get_settings()
    client = get_bq_client()
    conn_resource = f"{settings.gcp_project}.{settings.bq_location}.{settings.bq_connection_id}"
    sql = f"SELECT * FROM EXTERNAL_QUERY('{conn_resource}', 'SELECT 1 AS ok');"
    result = list(client.query(sql).result())
    assert len(result) > 0
    assert result[0]["ok"] == 1
