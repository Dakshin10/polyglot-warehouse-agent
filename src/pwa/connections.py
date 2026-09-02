import os
import re
import logging
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from google.cloud import bigquery
from pwa.settings import get_settings

logger = logging.getLogger("db")


def mask_credentials(text_msg: str) -> str:
    """Mask passwords and credentials in DSN URLs or error logs."""
    if not text_msg:
        return ""
    masked = re.sub(r":([^/@:]+)@", r":****@", str(text_msg))
    return masked


def get_mysql_engine():
    """Create SQLAlchemy engine for Aiven MySQL database with mandatory SSL and five-digit port."""
    settings = get_settings()

    host = settings.mysql_host
    port = settings.mysql_port
    user = settings.mysql_user
    password = settings.mysql_password
    dbname = settings.mysql_db
    ssl_ca = str(settings.mysql_ssl_ca)

    encoded_pwd = quote_plus(password) if password else ""
    db_uri = f"mysql+pymysql://{user}:{encoded_pwd}@{host}:{port}/{dbname}?charset=utf8mb4"

    connect_args = {"connect_timeout": 30}
    if os.path.exists(ssl_ca) and os.path.getsize(ssl_ca) > 0:
        connect_args["ssl"] = {"ca": os.path.abspath(ssl_ca)}
    else:
        connect_args["ssl"] = {"check_hostname": False}

    try:
        root_uri = f"mysql+pymysql://{user}:{encoded_pwd}@{host}:{port}/defaultdb?charset=utf8mb4"
        root_engine = create_engine(root_uri, connect_args=connect_args, pool_pre_ping=True)
        with root_engine.connect() as conn:
            conn.execute(
                text(f"CREATE DATABASE IF NOT EXISTS `{dbname}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            )
            conn.commit()
    except Exception:
        pass

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


def get_bq_client(project: str = "", location: str = "") -> bigquery.Client:
    """Create BigQuery client for project and location."""
    load_dotenv()
    proj = project or os.getenv("GCP_PROJECT", "").strip()
    loc = location or os.getenv("BQ_LOCATION", "EU").strip()
    return bigquery.Client(project=proj, location=loc)
