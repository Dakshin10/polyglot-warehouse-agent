import pytest
from pathlib import Path

PWA_ENV_VARS = (
    "KAGGLE_USERNAME",
    "KAGGLE_KEY",
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DB",
    "MYSQL_SSL_CA",
    "PG_CONNECT_MODE",
    "PG_HOST",
    "PG_PORT",
    "PG_USER",
    "PG_PASSWORD",
    "PG_DB",
    "PG_INSTANCE_CONNECTION_NAME",
    "PG_BQ_READER_USER",
    "PG_BQ_READER_PASSWORD",
    "GCP_PROJECT",
    "BQ_LOCATION",
    "BQ_CONNECTION_ID",
    "BQ_DS_REGISTRY",
    "BQ_DS_CREDITS",
    "BQ_DS_FILES",
    "BQ_DS_MART",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Unit tests must not depend on a .env or on values a previous test loaded into os.environ."""
    for key in PWA_ENV_VARS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def empty_env_file(tmp_path) -> str:
    path = tmp_path / ".env.empty"
    path.write_text("")
    return str(path)


@pytest.fixture
def ca_file(tmp_path) -> Path:
    """A stand-in for certs/ca.pem, so settings validation has a CA that exists."""
    path = tmp_path / "ca.pem"
    path.write_text("-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n")
    return path


@pytest.fixture
def valid_env(monkeypatch, ca_file):
    """A complete, valid environment. Individual tests break one rule at a time."""
    values = {
        "KAGGLE_USERNAME": "user",
        "KAGGLE_KEY": "key",
        "MYSQL_HOST": "host.aivencloud.com",
        "MYSQL_PORT": "26701",
        "MYSQL_PASSWORD": "pwd",
        "MYSQL_SSL_CA": str(ca_file),
        "PG_CONNECT_MODE": "connector",
        "PG_PASSWORD": "pwd",
        "PG_INSTANCE_CONNECTION_NAME": "proj:europe-west1:inst",
        "PG_BQ_READER_PASSWORD": "pwd",
        "GCP_PROJECT": "proj",
        "BQ_LOCATION": "EU",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_metadata_csv(fixtures_dir: Path) -> Path:
    return fixtures_dir / "movies_metadata_sample.csv"


@pytest.fixture
def sample_credits_csv(fixtures_dir: Path) -> Path:
    return fixtures_dir / "credits_sample.csv"


@pytest.fixture
def sample_sha256_file(fixtures_dir: Path) -> Path:
    return fixtures_dir / "selected_movie_ids.sha256"
