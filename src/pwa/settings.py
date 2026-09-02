"""Single source of truth for configuration.

Every environment variable the project reads is read here and nowhere else.
Validation collects *all* problems and raises once, listing them together, so a
misconfigured environment is fixed in one pass instead of one variable per run.
"""

import os
import re
from pathlib import Path
from typing import Literal
from dataclasses import dataclass, fields
from dotenv import load_dotenv

SECRET_FIELD_MARKERS = ("password", "key", "secret", "token")

# A value is a forbidden local-file database target if it is a sqlite URL or
# points at a local database file. Matching on the whole value (not a bare
# substring) keeps unrelated variables that merely contain ".db" from failing
# the whole configuration.
_SQLITE_TARGET = re.compile(r"^sqlite(\+\w+)?://|\.(db|sqlite|sqlite3)$", re.IGNORECASE)


def _normalize_region(region: str) -> str:
    """Map a Cloud SQL region to the BigQuery multi-region that covers it."""
    region_lower = region.lower().strip()
    if region_lower.startswith("europe-west") or region_lower.startswith("europe-north"):
        return "EU"
    if region_lower.startswith("us-") or region_lower.startswith("northamerica-"):
        return "US"
    return region_lower.upper()


@dataclass(frozen=True)
class Settings:
    # Kaggle
    kaggle_username: str
    kaggle_key: str

    # Aiven MySQL
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_db: str
    mysql_ssl_ca: Path

    # Cloud SQL Postgres
    pg_connect_mode: Literal["direct", "connector"]
    pg_host: str
    pg_port: int
    pg_user: str
    pg_password: str
    pg_db: str
    pg_instance_connection_name: str
    pg_bq_reader_user: str
    pg_bq_reader_password: str

    # BigQuery
    gcp_project: str
    bq_location: str
    bq_connection_id: str
    bq_ds_registry: str
    bq_ds_credits: str
    bq_ds_files: str
    bq_ds_mart: str

    @classmethod
    def from_env(cls, env_file: str | None = None) -> "Settings":
        """Load settings from the environment and validate every rule, reporting all failures at once."""
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        errors: list[str] = []

        def get_val(key: str, default: str = "") -> str:
            return os.getenv(key, default).strip()

        # Rule 6: no setting may point at a .db / .sqlite / sqlite:// target.
        for key, val in os.environ.items():
            if val and _SQLITE_TARGET.search(val.strip()):
                errors.append(
                    f"SQLite target forbidden in setting {key}='{val}' (this project has no local-file store)"
                )

        kaggle_username = get_val("KAGGLE_USERNAME")
        kaggle_key = get_val("KAGGLE_KEY")
        mysql_host = get_val("MYSQL_HOST")
        mysql_port_str = get_val("MYSQL_PORT")
        mysql_user = get_val("MYSQL_USER", "avnadmin")
        mysql_password = get_val("MYSQL_PASSWORD")
        mysql_db = get_val("MYSQL_DB", "movie_registry")
        mysql_ssl_ca_str = get_val("MYSQL_SSL_CA", "./certs/ca.pem")

        pg_connect_mode = get_val("PG_CONNECT_MODE", "connector").lower()
        pg_host = get_val("PG_HOST")
        pg_port_str = get_val("PG_PORT", "5432")
        pg_user = get_val("PG_USER", "loader")
        pg_password = get_val("PG_PASSWORD")
        pg_db = get_val("PG_DB", "movie_credits")
        pg_instance_connection_name = get_val("PG_INSTANCE_CONNECTION_NAME")
        pg_bq_reader_user = get_val("PG_BQ_READER_USER", "bqreader")
        pg_bq_reader_password = get_val("PG_BQ_READER_PASSWORD")

        gcp_project = get_val("GCP_PROJECT")
        bq_location = get_val("BQ_LOCATION", "EU")
        bq_connection_id = get_val("BQ_CONNECTION_ID", "movie-credits-conn")
        bq_ds_registry = get_val("BQ_DS_REGISTRY", "raw_registry")
        bq_ds_credits = get_val("BQ_DS_CREDITS", "raw_credits")
        bq_ds_files = get_val("BQ_DS_FILES", "raw_files")
        bq_ds_mart = get_val("BQ_DS_MART", "mart")

        # Rule 1: every required variable present and non-empty.
        required = {
            "MYSQL_HOST": mysql_host,
            "MYSQL_PASSWORD": mysql_password,
            "PG_PASSWORD": pg_password,
            "PG_INSTANCE_CONNECTION_NAME": pg_instance_connection_name,
            "PG_BQ_READER_PASSWORD": pg_bq_reader_password,
            "GCP_PROJECT": gcp_project,
        }
        missing_required = [k for k, v in required.items() if not v]
        if missing_required:
            errors.append(f"Missing required environment variables: {', '.join(missing_required)}")

        # Rule 2: MYSQL_PORT is an integer and is not 3306 (Aiven ports are five digits).
        mysql_port = 0
        if not mysql_port_str:
            errors.append("MYSQL_PORT is required.")
        else:
            try:
                mysql_port = int(mysql_port_str)
                if mysql_port == 3306:
                    errors.append("MYSQL_PORT cannot be 3306. Aiven MySQL requires a 5-digit port.")
            except ValueError:
                errors.append(f"MYSQL_PORT must be an integer, got '{mysql_port_str}'.")

        # Rule 3: MYSQL_SSL_CA must exist on disk and be non-empty.
        mysql_ssl_ca = Path(mysql_ssl_ca_str).expanduser().resolve()
        if not mysql_ssl_ca.is_file():
            errors.append(
                f"MYSQL_SSL_CA does not exist on disk: '{mysql_ssl_ca}'. "
                "Download the Aiven service CA certificate for this MySQL service "
                "(Aiven console -> service -> Overview -> CA certificate) and save it there. "
                "Without it the MySQL connection cannot verify the server's identity."
            )
        elif mysql_ssl_ca.stat().st_size == 0:
            errors.append(f"MYSQL_SSL_CA exists but is empty: '{mysql_ssl_ca}'.")

        # Rule 4: PG_INSTANCE_CONNECTION_NAME must be PROJECT:REGION:INSTANCE.
        cloud_sql_region = ""
        if pg_instance_connection_name:
            if re.match(r"^[^:]+:[^:]+:[^:]+$", pg_instance_connection_name):
                cloud_sql_region = pg_instance_connection_name.split(":")[1]
            else:
                errors.append(
                    "PG_INSTANCE_CONNECTION_NAME must match 'PROJECT:REGION:INSTANCE', "
                    f"got '{pg_instance_connection_name}'"
                )

        # Rule 5: BQ_LOCATION must be compatible with the Cloud SQL region.
        if cloud_sql_region:
            expected_bq_location = _normalize_region(cloud_sql_region)
            normalized_bq_location = bq_location.upper()
            if normalized_bq_location not in (expected_bq_location, cloud_sql_region.upper()):
                errors.append(
                    f"BQ_LOCATION '{bq_location}' is incompatible with Cloud SQL region "
                    f"'{cloud_sql_region}' (expected '{expected_bq_location}' or '{cloud_sql_region}'). "
                    "A mismatch surfaces later as a 'not found' error that never mentions location."
                )

        if pg_connect_mode not in ("direct", "connector"):
            errors.append(f"PG_CONNECT_MODE must be 'direct' or 'connector', got '{pg_connect_mode}'")

        pg_port = 5432
        if pg_port_str:
            try:
                pg_port = int(pg_port_str)
            except ValueError:
                errors.append(f"PG_PORT must be an integer, got '{pg_port_str}'.")

        if pg_connect_mode == "direct" and not pg_host:
            errors.append("PG_CONNECT_MODE is 'direct' but PG_HOST is empty.")

        if errors:
            raise ValueError("Configuration validation failed:\n  - " + "\n  - ".join(errors))

        return cls(
            kaggle_username=kaggle_username,
            kaggle_key=kaggle_key,
            mysql_host=mysql_host,
            mysql_port=mysql_port,
            mysql_user=mysql_user,
            mysql_password=mysql_password,
            mysql_db=mysql_db,
            mysql_ssl_ca=mysql_ssl_ca,
            pg_connect_mode=pg_connect_mode,  # type: ignore[arg-type]
            pg_host=pg_host,
            pg_port=pg_port,
            pg_user=pg_user,
            pg_password=pg_password,
            pg_db=pg_db,
            pg_instance_connection_name=pg_instance_connection_name,
            pg_bq_reader_user=pg_bq_reader_user,
            pg_bq_reader_password=pg_bq_reader_password,
            gcp_project=gcp_project,
            bq_location=bq_location,
            bq_connection_id=bq_connection_id,
            bq_ds_registry=bq_ds_registry,
            bq_ds_credits=bq_ds_credits,
            bq_ds_files=bq_ds_files,
            bq_ds_mart=bq_ds_mart,
        )

    def redacted_rows(self) -> list[tuple[str, str]]:
        """Every setting as (name, value) with secrets rendered as ***."""
        rows: list[tuple[str, str]] = []
        for f in fields(self):
            value = getattr(self, f.name)
            if any(marker in f.name for marker in SECRET_FIELD_MARKERS):
                rows.append((f.name, "***" if value else "(empty)"))
            else:
                rows.append((f.name, str(value) if str(value) else "(empty)"))
        return rows


def get_settings() -> Settings:
    """Load and validate settings. Raises ValueError listing every problem found."""
    return Settings.from_env()
