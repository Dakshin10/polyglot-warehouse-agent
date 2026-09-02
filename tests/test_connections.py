"""Integration tests against the live cloud stores.

Deselected by default (`addopts = -m 'not integration'`); run them with
`pytest -m integration`. They require a valid .env and credentials.
"""

import pytest
from sqlalchemy import text

from pwa.connections import get_bq_client, get_mysql_engine, get_pg_engine
from pwa.settings import get_settings


@pytest.mark.integration
def test_mysql_connection():
    """Aiven MySQL answers, and the connection is actually encrypted."""
    engine, engine_type = get_mysql_engine()
    assert engine_type == "aiven_mysql"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1;")).scalar() == 1
        cipher = conn.execute(text("SHOW STATUS LIKE 'Ssl_cipher'")).fetchone()
        assert cipher and cipher[1], "Ssl_cipher is blank: the MySQL connection is not encrypted"


@pytest.mark.integration
def test_postgres_connection():
    """Cloud SQL PostgreSQL answers through the configured connect mode."""
    engine, engine_type = get_pg_engine()
    assert engine_type in ("cloud_sql_connector", "cloud_sql_direct", "alloydb_connector")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1;")).scalar() == 1


@pytest.mark.integration
def test_federation():
    """BigQuery reaches Cloud SQL through EXTERNAL_QUERY."""
    settings = get_settings()
    client = get_bq_client()
    conn_resource = f"{settings.gcp_project}.{settings.bq_location}.{settings.bq_connection_id}"
    result = list(client.query(f"SELECT * FROM EXTERNAL_QUERY('{conn_resource}', 'SELECT 1 AS ok');").result())
    assert len(result) > 0
    assert result[0]["ok"] == 1
