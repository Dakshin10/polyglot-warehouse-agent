import pytest
from pwa.settings import Settings


def test_config_missing_required(monkeypatch, tmp_path):
    """Missing required variables should list all missing keys in error message."""
    empty_env = tmp_path / ".env.empty"
    empty_env.write_text("")

    for k in [
        "KAGGLE_USERNAME",
        "KAGGLE_KEY",
        "MYSQL_HOST",
        "MYSQL_PASSWORD",
        "PG_PASSWORD",
        "PG_INSTANCE_CONNECTION_NAME",
        "PG_BQ_READER_PASSWORD",
        "GCP_PROJECT",
    ]:
        monkeypatch.delenv(k, raising=False)

    with pytest.raises(ValueError) as excinfo:
        Settings.from_env(env_file=str(empty_env))

    err_msg = str(excinfo.value)
    assert "MYSQL_HOST" in err_msg
    assert "MYSQL_PASSWORD" in err_msg
    assert "GCP_PROJECT" in err_msg


def test_config_mysql_port_3306(monkeypatch, tmp_path):
    """Aiven MySQL port cannot be 3306."""
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("dummy")

    monkeypatch.setenv("KAGGLE_USERNAME", "user")
    monkeypatch.setenv("KAGGLE_KEY", "key")
    monkeypatch.setenv("MYSQL_HOST", "host.aivencloud.com")
    monkeypatch.setenv("MYSQL_PORT", "3306")
    monkeypatch.setenv("MYSQL_PASSWORD", "pwd")
    monkeypatch.setenv("MYSQL_SSL_CA", str(ca_file))
    monkeypatch.setenv("PG_PASSWORD", "pwd")
    monkeypatch.setenv("PG_INSTANCE_CONNECTION_NAME", "proj:europe-west1:inst")
    monkeypatch.setenv("PG_BQ_READER_PASSWORD", "pwd")
    monkeypatch.setenv("GCP_PROJECT", "proj")

    with pytest.raises(ValueError) as excinfo:
        Settings.from_env()

    assert "MYSQL_PORT cannot be 3306" in str(excinfo.value)


def test_config_sqlite_rejection(monkeypatch, tmp_path):
    """Setting pointing to .db or sqlite target must raise ValueError."""
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("dummy")

    monkeypatch.setenv("KAGGLE_USERNAME", "user")
    monkeypatch.setenv("KAGGLE_KEY", "key")
    monkeypatch.setenv("MYSQL_HOST", "host.aivencloud.com")
    monkeypatch.setenv("MYSQL_PORT", "26701")
    monkeypatch.setenv("MYSQL_PASSWORD", "pwd")
    monkeypatch.setenv("MYSQL_SSL_CA", str(ca_file))
    monkeypatch.setenv("PG_PASSWORD", "pwd")
    monkeypatch.setenv("PG_INSTANCE_CONNECTION_NAME", "proj:europe-west1:inst")
    monkeypatch.setenv("PG_BQ_READER_PASSWORD", "pwd")
    monkeypatch.setenv("GCP_PROJECT", "proj")
    monkeypatch.setenv("MY_SQLITE_TARGET", "sqlite:///test.db")

    with pytest.raises(ValueError) as excinfo:
        Settings.from_env()

    assert "SQLite target forbidden" in str(excinfo.value)


def test_config_region_location_mismatch(monkeypatch, tmp_path):
    """BQ location mismatch with Cloud SQL region must raise ValueError."""
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("dummy")

    monkeypatch.setenv("KAGGLE_USERNAME", "user")
    monkeypatch.setenv("KAGGLE_KEY", "key")
    monkeypatch.setenv("MYSQL_HOST", "host.aivencloud.com")
    monkeypatch.setenv("MYSQL_PORT", "26701")
    monkeypatch.setenv("MYSQL_PASSWORD", "pwd")
    monkeypatch.setenv("MYSQL_SSL_CA", str(ca_file))
    monkeypatch.setenv("PG_PASSWORD", "pwd")
    monkeypatch.setenv("PG_INSTANCE_CONNECTION_NAME", "proj:europe-west1:inst")
    monkeypatch.setenv("PG_BQ_READER_PASSWORD", "pwd")
    monkeypatch.setenv("GCP_PROJECT", "proj")
    monkeypatch.setenv("BQ_LOCATION", "US")  # Mismatch with europe-west1

    with pytest.raises(ValueError) as excinfo:
        Settings.from_env()

    assert "incompatible with Cloud SQL region" in str(excinfo.value)
