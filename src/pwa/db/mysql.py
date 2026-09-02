import os
import re
import logging
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from pwa.config import get_settings

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
