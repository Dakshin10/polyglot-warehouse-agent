import pytest
from pwa.db import get_bq_client
from pwa.config import get_settings


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
