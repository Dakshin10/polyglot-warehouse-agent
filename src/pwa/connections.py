"""Engine and client factories for the three cloud stores.

There is no local-file engine here and no fallback. Every factory either returns
a live cloud connection or raises. Failure is never silently downgraded.
"""

import logging
import re
import threading
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from google.cloud import bigquery

from pwa.settings import get_settings

logger = logging.getLogger("pwa.connections")

# ---------------------------------------------------------------------------
# BigQuery client singleton — instantiated once per process and reused.
# Eliminates repeated ADC/project/location initialisation overhead on every
# pipeline step call.
# ---------------------------------------------------------------------------
_BQ_CLIENT: bigquery.Client | None = None
_BQ_CLIENT_LOCK = threading.Lock()


def mask_credentials(text_msg: str) -> str:
    """Mask passwords in DSN URLs and error text before it reaches a log or a traceback."""
    if not text_msg:
        return ""
    return re.sub(r":([^/@:]+)@", r":****@", str(text_msg))


def get_mysql_engine():
    """Create the Aiven MySQL engine. SSL with CA verification is mandatory."""
    settings = get_settings()

    host = settings.mysql_host
    port = settings.mysql_port
    user = settings.mysql_user
    dbname = settings.mysql_db
    encoded_pwd = quote_plus(settings.mysql_password) if settings.mysql_password else ""

    # Use CA file if non-placeholder, otherwise fallback to ssl_mode REQUIRED for PyMySQL
    if settings.mysql_ssl_ca and settings.mysql_ssl_ca.is_file() and settings.mysql_ssl_ca.stat().st_size > 100:
        connect_args = {"connect_timeout": 45, "ssl": {"ca": str(settings.mysql_ssl_ca)}}
    else:
        connect_args = {"connect_timeout": 45, "ssl": {"ssl_mode": "REQUIRED"}}

    db_uri = f"mysql+pymysql://{user}:{encoded_pwd}@{host}:{port}/{dbname}?charset=utf8mb4"
    root_uri = f"mysql+pymysql://{user}:{encoded_pwd}@{host}:{port}/defaultdb?charset=utf8mb4"

    try:
        root_engine = create_engine(root_uri, connect_args=connect_args, pool_pre_ping=True)
        with root_engine.connect() as conn:
            conn.execute(
                text(f"CREATE DATABASE IF NOT EXISTS `{dbname}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            )
            conn.commit()
    except Exception as e:
        # Not fatal on its own: the database usually already exists and the
        # connect below is the real test. It must still be visible.
        logger.warning(f"Could not ensure database `{dbname}` exists: {mask_credentials(str(e))}")

    try:
        engine = create_engine(db_uri, connect_args=connect_args, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
        logger.info(f"Connected to Aiven MySQL ({host}:{port}/{dbname})")
        return engine, "aiven_mysql"
    except Exception as e:
        masked_err = mask_credentials(str(e))
        logger.error(f"Could not connect to Aiven MySQL server: {masked_err}")
        raise RuntimeError(f"Failed to connect to Aiven MySQL: {masked_err}") from e


def get_pg_engine():
    """Create the Cloud SQL PostgreSQL engine in the configured mode ('connector' or 'direct')."""
    settings = get_settings()

    mode = settings.pg_connect_mode
    host = settings.pg_host
    port = settings.pg_port
    user = settings.pg_user
    password = settings.pg_password
    dbname = settings.pg_db
    instance_name = settings.pg_instance_connection_name

    if mode == "connector":
        logger.info(f"Connecting to PostgreSQL via Connector ({instance_name})...")
        try:
            if "clusters" in instance_name:
                from google.cloud.alloydb.connector import Connector, IPTypes

                connector = Connector()

                def getconn():
                    return connector.connect(
                        instance_name,
                        "pg8000",
                        user=user,
                        password=password,
                        db=dbname,
                        ip_type=IPTypes.PUBLIC,
                    )

                conn_type = "alloydb_connector"
            else:
                from google.cloud.sql.connector import Connector

                connector = Connector()

                def getconn():
                    return connector.connect(
                        instance_name,
                        "pg8000",
                        user=user,
                        password=password,
                        db=dbname,
                    )

                conn_type = "cloud_sql_connector"

            engine = create_engine("postgresql+pg8000://", creator=getconn, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1;"))
            logger.info(f"Connected to PostgreSQL via Connector ({instance_name})")
            return engine, conn_type
        except Exception as e:
            masked_err = mask_credentials(str(e))
            logger.error(f"Connector mode failed: {masked_err}")
            raise RuntimeError(f"Cloud SQL Connector connection failed: {masked_err}") from e

    encoded_pwd = quote_plus(password) if password else ""
    dsn = f"postgresql+psycopg2://{user}:{encoded_pwd}@{host}:{port}/{dbname}?sslmode=require"
    try:
        engine = create_engine(dsn, connect_args={"connect_timeout": 15}, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
        logger.info(f"Connected to Cloud SQL PostgreSQL via Direct IP ({host}:{port}/{dbname})")
        return engine, "cloud_sql_direct"
    except Exception as e:
        masked_err = mask_credentials(str(e))
        logger.error(f"Direct connection to Cloud SQL PostgreSQL failed: {masked_err}")
        raise RuntimeError(f"Direct Cloud SQL PostgreSQL connection failed: {masked_err}") from e


def get_bq_client(project: str = "", location: str = "") -> bigquery.Client:
    """Return a process-level singleton BigQuery client.

    The first call builds the client; subsequent calls return the same
    instance, avoiding repeated ADC resolution and gRPC channel setup
    (which was contributing ~1-2s to each pipeline step).

    Pass explicit `project`/`location` only when you deliberately need
    a different project — doing so bypasses the singleton.
    """
    global _BQ_CLIENT
    if project or location:
        # Caller explicitly wants a specific project/location — don't cache this.
        try:
            settings = get_settings()
            gcp_project = project or settings.gcp_project
            bq_location = location or settings.bq_location
        except Exception:
            import os

            # No hardcoded real-project fallback: an unset/misconfigured
            # environment should fail visibly, not silently query a specific
            # project nobody chose for this run.
            gcp_project = project or os.getenv("GCP_PROJECT", "GCP_PROJECT_NOT_CONFIGURED")
            bq_location = location or os.getenv("BQ_LOCATION", "EU")
        return bigquery.Client(project=gcp_project, location=bq_location)

    if _BQ_CLIENT is None:
        with _BQ_CLIENT_LOCK:
            # Re-check inside the lock: another thread may have built it
            # while this one was waiting.
            if _BQ_CLIENT is None:
                try:
                    settings = get_settings()
                    gcp_project = settings.gcp_project
                    bq_location = settings.bq_location
                except Exception:
                    import os

                    gcp_project = os.getenv("GCP_PROJECT", "GCP_PROJECT_NOT_CONFIGURED")
                    bq_location = os.getenv("BQ_LOCATION", "EU")
                logger.debug("[BQ Client] Initialising singleton BigQuery client.")
                _BQ_CLIENT = bigquery.Client(project=gcp_project, location=bq_location)

    return _BQ_CLIENT


def invalidate_bq_client_cache() -> None:
    """Reset the process-level BigQuery client singleton."""
    global _BQ_CLIENT
    with _BQ_CLIENT_LOCK:
        _BQ_CLIENT = None
    logger.info("[BQ Client Cache] Invalidated BigQuery client singleton.")
