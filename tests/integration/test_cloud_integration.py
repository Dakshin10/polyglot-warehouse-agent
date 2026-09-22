"""Live cloud integration test suite for PWA enterprise data platform.

Skipped by default in local offline test runs.
Executes only when PWA_INTEGRATION_TESTS=1 environment variable is set.
"""

import os
import unittest


class TestCloudIntegration(unittest.TestCase):
    def setUp(self):
        if os.getenv("PWA_INTEGRATION_TESTS", "0").lower() not in ("1", "true", "yes"):
            self.skipTest("Live cloud integration tests skipped (PWA_INTEGRATION_TESTS != 1)")

    def test_live_bigquery_connectivity(self):
        """Test live connection to GCP BigQuery when credentials are present."""
        from pwa.connections import get_bq_client

        client = get_bq_client()
        query_job = client.query("SELECT 1 AS num;")
        df = query_job.to_dataframe()
        self.assertEqual(df["num"].iloc[0], 1)

    def test_live_postgres_connectivity(self):
        """Test live connection to Cloud SQL PostgreSQL when configured."""
        from pwa.settings import get_settings

        settings = get_settings()
        if not settings.pg_enabled:
            self.skipTest("Cloud SQL PostgreSQL is not enabled in settings.")
        from pwa.ingestion.connectors.postgres_connector import PostgreSQLConnector

        conn = PostgreSQLConnector(
            "alloydb",
            {
                "host": settings.pg_host,
                "port": settings.pg_port,
                "database": settings.pg_db,
                "user": settings.pg_user,
                "password": settings.pg_password,
            },
        )
        self.assertTrue(conn.test_connection())

    def test_live_mysql_connectivity(self):
        """Test live connection to Aiven MySQL when configured."""
        from pwa.settings import get_settings

        settings = get_settings()
        if not settings.mysql_enabled:
            self.skipTest("Aiven MySQL is not enabled in settings.")
        from pwa.ingestion.connectors.mysql_connector import MySQLConnector

        conn = MySQLConnector(
            "aiven_mysql",
            {
                "host": settings.mysql_host,
                "port": settings.mysql_port,
                "database": settings.mysql_db,
                "user": settings.mysql_user,
                "password": settings.mysql_password,
            },
        )
        self.assertTrue(conn.test_connection())


if __name__ == "__main__":
    unittest.main()
