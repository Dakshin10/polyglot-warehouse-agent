import logging
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from pwa.config import get_settings
from .mysql import mask_credentials

logger = logging.getLogger("db")


def get_pg_engine():
    """Create SQLAlchemy engine for Cloud SQL PostgreSQL using direct or connector mode."""
    settings = get_settings()

    mode = settings.pg_connect_mode
    host = settings.pg_host
    port = settings.pg_port
    user = settings.pg_user
    password = settings.pg_password
    dbname = settings.pg_db
    instance_name = settings.pg_instance_connection_name

    encoded_pwd = quote_plus(password) if password else ""

    if mode == "connector":
        logger.info(f"Connecting to PostgreSQL via Connector ({instance_name})...")
        try:
            if not instance_name:
                raise ValueError("PG_INSTANCE_CONNECTION_NAME not configured.")
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

    # Direct mode
    dsn = f"postgresql+psycopg2://{user}:{encoded_pwd}@{host}:{port}/{dbname}?sslmode=require"
    try:
        if not host or host == "localhost":
            raise ValueError("PG_HOST not configured for Cloud SQL PostgreSQL.")
        engine = create_engine(dsn, connect_args={"connect_timeout": 15}, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
        logger.info(f"Connected to Cloud SQL PostgreSQL via Direct IP ({host}:{port}/{dbname})")
        return engine, "cloud_sql_direct"
    except Exception as e:
        masked_err = mask_credentials(str(e))
        logger.error(f"Direct connection to Cloud SQL PostgreSQL failed: {masked_err}")
        raise RuntimeError(f"Direct Cloud SQL PostgreSQL connection failed: {masked_err}") from e
