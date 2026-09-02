import os
import re
from pathlib import Path
from typing import Literal
from dataclasses import dataclass
from dotenv import load_dotenv


def _normalize_region(region: str) -> str:
    """Map Cloud SQL region to standard BQ multi-region or region string."""
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
        """Load settings from environment and validate all rules."""
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        errors: list[str] = []

        def get_val(key: str, default: str = "") -> str:
            return os.getenv(key, default).strip()

        # Check for SQLite / .db settings rejection first
        for key, val in os.environ.items():
            val_lower = val.lower()
            if ".db" in val_lower or ".sqlite" in val_lower or "sqlite://" in val_lower:
                errors.append(f"SQLite target forbidden in setting {key}='{val}'")

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

        missing_required = []
        if not mysql_host:
            missing_required.append("MYSQL_HOST")
        if not mysql_password:
            missing_required.append("MYSQL_PASSWORD")
        if not pg_password:
            missing_required.append("PG_PASSWORD")
        if not pg_instance_connection_name:
            missing_required.append("PG_INSTANCE_CONNECTION_NAME")
        if not pg_bq_reader_password:
            missing_required.append("PG_BQ_READER_PASSWORD")
        if not gcp_project:
            missing_required.append("GCP_PROJECT")

        if missing_required:
            errors.append(f"Missing required environment variables: {', '.join(missing_required)}")

        # 2. mysql_port is integer and not 3306
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

        # 3. mysql_ssl_ca Path
        mysql_ssl_ca = Path(mysql_ssl_ca_str).resolve()

        # 4. pg_instance_connection_name regex match PROJECT:REGION:INSTANCE
        if pg_instance_connection_name and not re.match(r"^[^:]+:[^:]+:[^:]+$", pg_instance_connection_name):
            errors.append(
                f"PG_INSTANCE_CONNECTION_NAME must match 'PROJECT:REGION:INSTANCE', got '{pg_instance_connection_name}'"
            )

        # 5. bq_location compatible with Cloud SQL region
        if pg_instance_connection_name and ":" in pg_instance_connection_name:
            parts = pg_instance_connection_name.split(":")
            if len(parts) == 3:
                cloud_sql_region = parts[1]
                expected_bq_location = _normalize_region(cloud_sql_region)
                normalized_bq_location = bq_location.upper()
                if (
                    normalized_bq_location != expected_bq_location
                    and normalized_bq_location != cloud_sql_region.upper()
                ):
                    errors.append(
                        f"BQ_LOCATION '{bq_location}' is incompatible with Cloud SQL region '{cloud_sql_region}' (expected '{expected_bq_location}')"
                    )

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
            pg_connect_mode=pg_connect_mode,  # type: ignore
            pg_host=pg_host,
            pg_port=int(pg_port_str) if pg_port_str.isdigit() else 5432,
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


def get_settings() -> Settings:
    """Lazy loader for singleton settings."""
    return Settings.from_env()
