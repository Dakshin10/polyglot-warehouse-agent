"""Single source of truth for configuration — Nexora Technologies Enterprise Platform.

Every environment variable the project reads is read here and nowhere else.
Validation collects *all* problems and raises once, listing them together, so a
misconfigured environment is fixed in one pass instead of one variable per run.

MySQL and PostgreSQL connections are retained as optional (not required by the
primary ingestion pipeline which uses BigQuery native tables). They can be
enabled for future live-source connectors.
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass, fields
from dotenv import load_dotenv

SECRET_FIELD_MARKERS = ("password", "key", "secret", "token")

_SQLITE_TARGET = re.compile(r"^sqlite(\+\w+)?://|\.( db|sqlite|sqlite3)$", re.IGNORECASE)

# Repository root (two levels above this file: src/pwa/settings.py → repo root)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class ProductionEnvironmentError(RuntimeError):
    """Raised when production environment rules are violated (e.g. mock fallbacks in production)."""

    pass


@dataclass(frozen=True)
class Settings:
    # ------------------------------------------------------------------
    # Environment Mode (development | testing | production)
    # ------------------------------------------------------------------
    pwa_env: str

    @property
    def is_production(self) -> bool:
        return self.pwa_env.lower() == "production"

    @property
    def is_testing(self) -> bool:
        return self.pwa_env.lower() in ("testing", "test")

    @property
    def is_development(self) -> bool:
        return self.pwa_env.lower() in ("development", "dev")

    # ------------------------------------------------------------------
    # Kaggle credentials
    # ------------------------------------------------------------------
    kaggle_username: str
    kaggle_key: str

    # ------------------------------------------------------------------
    # Google Cloud Platform / BigQuery (required)
    # ------------------------------------------------------------------
    gcp_project: str
    bq_location: str

    # BigQuery dataset names — raw layer
    bq_ds_raw_aw: str  # raw_adventureworks
    bq_ds_raw_olist: str  # raw_olist
    bq_ds_raw_marketing: str  # raw_olist_marketing

    # BigQuery dataset names — staging layer
    bq_ds_staging_ent: str  # staging_enterprise
    bq_ds_staging_mkt: str  # staging_marketplace

    # BigQuery dataset names — curated layer
    bq_ds_curated_ent: str  # curated_enterprise
    bq_ds_curated_mkt: str  # curated_marketplace

    # BigQuery dataset name — control plane / metadata
    bq_ds_metadata: str  # pwa_metadata

    # BigQuery dataset name — rollup / fast-path materializations
    bq_ds_rollup: str  # rollup

    # BigQuery dataset name — governed business-surface mart views
    bq_ds_mart: str  # mart

    # ------------------------------------------------------------------
    # Optional: Aiven MySQL (not required by primary ingestion pipeline)
    # ------------------------------------------------------------------
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_db: str
    mysql_ssl_ca: Path
    mysql_enabled: bool  # True only if host+password are configured

    # ------------------------------------------------------------------
    # Optional: Cloud SQL PostgreSQL (not required by primary ingestion pipeline)
    # ------------------------------------------------------------------
    pg_connect_mode: str
    pg_host: str
    pg_port: int
    pg_user: str
    pg_password: str
    pg_db: str
    pg_instance_connection_name: str
    pg_bq_reader_user: str
    pg_bq_reader_password: str
    pg_enabled: bool  # True only if instance_connection_name+password configured

    # BigQuery connection ID for Cloud SQL federation (optional)
    bq_connection_id: str

    # ------------------------------------------------------------------
    # Local paths
    # ------------------------------------------------------------------
    source_base_dir: Path  # data/source/
    manifest_dir: Path  # data/manifests/

    @classmethod
    def from_env(cls, env_file: str | None = None) -> "Settings":
        """Load settings from the environment and validate, reporting all failures at once."""
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        errors: list[str] = []

        def get_val(key: str, default: str = "") -> str:
            return os.getenv(key, default).strip()

        # Reject SQLite targets throughout (this is a cloud-native platform)
        for key, val in os.environ.items():
            if val and _SQLITE_TARGET.search(val.strip()):
                errors.append(
                    f"SQLite target forbidden in {key}='{val}' (this project uses BigQuery, not local file stores)"
                )

        # ------------------------------------------------------------------
        # Kaggle
        # ------------------------------------------------------------------
        kaggle_username = get_val("KAGGLE_USERNAME")
        kaggle_key = get_val("KAGGLE_KEY")

        # ------------------------------------------------------------------
        # BigQuery (required)
        # ------------------------------------------------------------------
        gcp_project = get_val("GCP_PROJECT")
        bq_location = get_val("BQ_LOCATION", "EU")

        bq_ds_raw_aw = get_val("BQ_DS_RAW_AW", "raw_adventureworks")
        bq_ds_raw_olist = get_val("BQ_DS_RAW_OLIST", "raw_olist")
        bq_ds_raw_marketing = get_val("BQ_DS_RAW_MARKETING", "raw_olist_marketing")
        bq_ds_staging_ent = get_val("BQ_DS_STAGING_ENT", "staging_enterprise")
        bq_ds_staging_mkt = get_val("BQ_DS_STAGING_MKT", "staging_marketplace")
        bq_ds_curated_ent = get_val("BQ_DS_CURATED_ENT", "curated_enterprise")
        bq_ds_curated_mkt = get_val("BQ_DS_CURATED_MKT", "curated_marketplace")
        bq_ds_metadata = get_val("BQ_DS_METADATA", "pwa_metadata")
        bq_ds_rollup = get_val("BQ_DS_ROLLUP", "rollup")
        bq_ds_mart = get_val("BQ_DS_MART", "mart")

        required_bq = {"GCP_PROJECT": gcp_project}
        for k, v in required_bq.items():
            if not v:
                errors.append(f"Missing required environment variable: {k}")

        # ------------------------------------------------------------------
        # Optional: Aiven MySQL
        # ------------------------------------------------------------------
        mysql_host = get_val("MYSQL_HOST")
        mysql_port_str = get_val("MYSQL_PORT", "0")
        mysql_user = get_val("MYSQL_USER", "avnadmin")
        mysql_password = get_val("MYSQL_PASSWORD")
        mysql_db = get_val("MYSQL_DB", "nexora_erp")
        mysql_ssl_ca_str = get_val("MYSQL_SSL_CA", "./certs/ca.pem")
        mysql_ssl_ca = Path(mysql_ssl_ca_str).expanduser().resolve()

        mysql_enabled = bool(mysql_host and mysql_password)
        mysql_port = 0
        if mysql_enabled:
            try:
                mysql_port = int(mysql_port_str)
                if mysql_port == 3306:
                    errors.append("MYSQL_PORT cannot be 3306 when using Aiven MySQL (requires a 5-digit port).")
            except ValueError:
                errors.append(f"MYSQL_PORT must be an integer, got '{mysql_port_str}'.")

            if not mysql_ssl_ca.is_file():
                errors.append(
                    f"MYSQL_SSL_CA does not exist on disk: '{mysql_ssl_ca}'. "
                    "Download the Aiven service CA certificate and save it there."
                )
            elif mysql_ssl_ca.stat().st_size == 0:
                errors.append(f"MYSQL_SSL_CA exists but is empty: '{mysql_ssl_ca}'.")

        # ------------------------------------------------------------------
        # Optional: Cloud SQL PostgreSQL
        # ------------------------------------------------------------------
        pg_connect_mode = get_val("PG_CONNECT_MODE", "connector").lower()
        pg_host = get_val("PG_HOST")
        pg_port_str = get_val("PG_PORT", "5432")
        pg_user = get_val("PG_USER", "loader")
        pg_password = get_val("PG_PASSWORD")
        pg_db = get_val("PG_DB", "nexora_marketplace")
        pg_instance_connection_name = get_val("PG_INSTANCE_CONNECTION_NAME")
        pg_bq_reader_user = get_val("PG_BQ_READER_USER", "bqreader")
        pg_bq_reader_password = get_val("PG_BQ_READER_PASSWORD")
        bq_connection_id = get_val("BQ_CONNECTION_ID", "nexora-source-conn")

        pg_enabled = bool(pg_instance_connection_name and pg_password)

        pg_port = 5432
        if pg_port_str:
            try:
                pg_port = int(pg_port_str)
            except ValueError:
                errors.append(f"PG_PORT must be an integer, got '{pg_port_str}'.")

        if pg_connect_mode not in ("direct", "connector"):
            errors.append(f"PG_CONNECT_MODE must be 'direct' or 'connector', got '{pg_connect_mode}'")

        if pg_enabled and pg_connect_mode == "direct" and not pg_host:
            errors.append("PG_CONNECT_MODE is 'direct' but PG_HOST is empty.")

        if pg_enabled and pg_instance_connection_name:
            if not re.match(r"^[^:]+:[^:]+:[^:]+$", pg_instance_connection_name):
                errors.append(
                    "PG_INSTANCE_CONNECTION_NAME must match 'PROJECT:REGION:INSTANCE', "
                    f"got '{pg_instance_connection_name}'"
                )

        # ------------------------------------------------------------------
        # Local paths
        # ------------------------------------------------------------------
        source_base_str = get_val("PWA_SOURCE_BASE_DIR", str(REPO_ROOT / "data" / "source"))
        manifest_dir_str = get_val("PWA_MANIFEST_DIR", str(REPO_ROOT / "data" / "manifests"))
        source_base_dir = Path(source_base_str).expanduser().resolve()
        manifest_dir = Path(manifest_dir_str).expanduser().resolve()

        if errors:
            raise ValueError("Configuration validation failed:\n  - " + "\n  - ".join(errors))

        pwa_env = get_val("PWA_ENV", "development").lower()

        return cls(
            pwa_env=pwa_env,
            kaggle_username=kaggle_username,
            kaggle_key=kaggle_key,
            gcp_project=gcp_project,
            bq_location=bq_location,
            bq_ds_raw_aw=bq_ds_raw_aw,
            bq_ds_raw_olist=bq_ds_raw_olist,
            bq_ds_raw_marketing=bq_ds_raw_marketing,
            bq_ds_staging_ent=bq_ds_staging_ent,
            bq_ds_staging_mkt=bq_ds_staging_mkt,
            bq_ds_curated_ent=bq_ds_curated_ent,
            bq_ds_curated_mkt=bq_ds_curated_mkt,
            bq_ds_metadata=bq_ds_metadata,
            bq_ds_rollup=bq_ds_rollup,
            bq_ds_mart=bq_ds_mart,
            mysql_host=mysql_host,
            mysql_port=mysql_port,
            mysql_user=mysql_user,
            mysql_password=mysql_password,
            mysql_db=mysql_db,
            mysql_ssl_ca=mysql_ssl_ca,
            mysql_enabled=mysql_enabled,
            pg_connect_mode=pg_connect_mode,  # type: ignore[arg-type]
            pg_host=pg_host,
            pg_port=pg_port,
            pg_user=pg_user,
            pg_password=pg_password,
            pg_db=pg_db,
            pg_instance_connection_name=pg_instance_connection_name,
            pg_bq_reader_user=pg_bq_reader_user,
            pg_bq_reader_password=pg_bq_reader_password,
            pg_enabled=pg_enabled,
            bq_connection_id=bq_connection_id,
            source_base_dir=source_base_dir,
            manifest_dir=manifest_dir,
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

    def all_bq_datasets(self) -> list[str]:
        """Return all BigQuery dataset IDs used by the platform."""
        return [
            self.bq_ds_raw_aw,
            self.bq_ds_raw_olist,
            self.bq_ds_raw_marketing,
            self.bq_ds_staging_ent,
            self.bq_ds_staging_mkt,
            self.bq_ds_curated_ent,
            self.bq_ds_curated_mkt,
            self.bq_ds_metadata,
            self.bq_ds_rollup,
            self.bq_ds_mart,
        ]

    def raw_datasets(self) -> list[str]:
        """Return raw-layer BigQuery dataset IDs."""
        return [self.bq_ds_raw_aw, self.bq_ds_raw_olist, self.bq_ds_raw_marketing]

    def curated_datasets(self) -> list[str]:
        """Return curated-layer BigQuery dataset IDs."""
        return [self.bq_ds_curated_ent, self.bq_ds_curated_mkt]


def get_settings() -> Settings:
    """Load and validate settings. Raises ValueError listing every problem found."""
    return Settings.from_env()
