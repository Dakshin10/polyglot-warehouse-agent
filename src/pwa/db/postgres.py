import os
import logging
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from .mysql import mask_credentials

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("db")

OUT_DIR = os.path.join(".", "data", "out")


def get_pg_engine():
    """Create SQLAlchemy engine for Cloud SQL PostgreSQL using direct or connector mode."""
    load_dotenv()
    mode = os.getenv("PG_CONNECT_MODE", "direct").lower().strip()
    host = os.getenv("PG_HOST", "").strip()
    port_str = os.getenv("PG_PORT", "").strip()
    port = int(port_str) if port_str.isdigit() else 5432
    user = os.getenv("PG_USER", "loader").strip()
    password = os.getenv("PG_PASSWORD", "").strip()
    dbname = os.getenv("PG_DB", "movie_credits").strip()
    instance_name = os.getenv("PG_INSTANCE_CONNECTION_NAME", "").strip()

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
            logger.warning(f"Connector mode failed: {masked_err}")

    # Direct mode (default)
    dsn = f"postgresql+psycopg2://{user}:{encoded_pwd}@{host}:{port}/{dbname}?sslmode=require"
    try:
        if not host or host == "localhost":
            raise ValueError("PG_HOST not configured for Cloud SQL PostgreSQL.")
        engine = create_engine(
            dsn,
            connect_args={"connect_timeout": 15},
            pool_pre_ping=True
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
        logger.info(f"Connected to Cloud SQL PostgreSQL via Direct IP ({host}:{port}/{dbname})")
        return engine, "cloud_sql_direct"
    except Exception as e:
        masked_err = mask_credentials(str(e))
        logger.warning(f"Direct connection to Cloud SQL PostgreSQL failed: {masked_err}")
        logger.warning("PROMPTING TROUBLESHOOTING: Check if your workstation IP is in Cloud SQL Authorized Networks, or set PG_CONNECT_MODE=connector in .env.")
        logger.warning("Falling back to local SQLite file database for `movie_credits` table.")
        os.makedirs(OUT_DIR, exist_ok=True)
        sqlite_path = os.path.abspath(os.path.join(OUT_DIR, "postgres_movie_credits.db"))
        sqlite_uri = f"sqlite:///{sqlite_path}"
        return create_engine(sqlite_uri), "sqlite"
