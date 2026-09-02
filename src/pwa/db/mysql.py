import os
import re
import logging
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("db")

OUT_DIR = os.path.join(".", "data", "out")


def mask_credentials(text_msg: str) -> str:
    """Mask passwords and credentials in DSN URLs or error logs."""
    if not text_msg:
        return ""
    masked = re.sub(r':([^/@:]+)@', r':****@', str(text_msg))
    return masked


def get_mysql_engine():
    """Create SQLAlchemy engine for Aiven MySQL database with mandatory SSL and five-digit port."""
    load_dotenv()
    host = os.getenv("MYSQL_HOST", "").strip()
    port_str = os.getenv("MYSQL_PORT", "").strip()
    port = int(port_str) if port_str.isdigit() else 3306
    user = os.getenv("MYSQL_USER", "avnadmin").strip()
    password = os.getenv("MYSQL_PASSWORD", "").strip()
    dbname = os.getenv("MYSQL_DB", "movie_registry").strip()
    ssl_ca = os.getenv("MYSQL_SSL_CA", "./certs/ca.pem").strip()

    if not host or host == "localhost":
        host = "localhost"

    encoded_pwd = quote_plus(password) if password else ""
    db_uri = f"mysql+pymysql://{user}:{encoded_pwd}@{host}:{port}/{dbname}?charset=utf8mb4"

    connect_args = {"connect_timeout": 30}
    if os.path.exists(ssl_ca) and os.path.getsize(ssl_ca) > 0:
        connect_args["ssl"] = {"ca": os.path.abspath(ssl_ca)}
    else:
        connect_args["ssl"] = {"check_hostname": False}

    try:
        if not host or host == "localhost":
            raise ValueError("MYSQL_HOST not configured for Aiven MySQL.")

        try:
            root_uri = f"mysql+pymysql://{user}:{encoded_pwd}@{host}:{port}/defaultdb?charset=utf8mb4"
            root_engine = create_engine(root_uri, connect_args=connect_args, pool_pre_ping=True)
            with root_engine.connect() as conn:
                conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{dbname}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
                conn.commit()
        except Exception:
            pass

        engine = create_engine(
            db_uri,
            connect_args=connect_args,
            pool_pre_ping=True
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
        logger.info(f"Connected to Aiven MySQL ({host}:{port}/{dbname})")
        return engine, "aiven_mysql"
    except Exception as e:
        masked_err = mask_credentials(str(e))
        logger.warning(f"Could not connect to Aiven MySQL server: {masked_err}")
        logger.warning("Falling back to local SQLite file database for `movie` table.")
        os.makedirs(OUT_DIR, exist_ok=True)
        sqlite_path = os.path.abspath(os.path.join(OUT_DIR, "mysql_movie.db"))
        sqlite_uri = f"sqlite:///{sqlite_path}"
        return create_engine(sqlite_uri), "sqlite"
