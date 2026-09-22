import pytest

from pwa.settings import Settings


def test_missing_required_lists_every_missing_key(empty_env_file):
    """Validation must report missing GCP_PROJECT required variable."""
    with pytest.raises(ValueError) as excinfo:
        Settings.from_env(env_file=empty_env_file)

    message = str(excinfo.value)
    assert "GCP_PROJECT" in message


def test_valid_environment_loads(valid_env):
    settings = Settings.from_env()
    assert settings.mysql_port == 26701
    assert settings.bq_location == "EU"
    assert settings.pg_instance_connection_name == "proj:europe-west1:inst"


def test_mysql_port_3306_rejected(valid_env, monkeypatch):
    """Aiven MySQL never listens on 3306; a 3306 port means the wrong host is configured."""
    monkeypatch.setenv("MYSQL_PORT", "3306")
    with pytest.raises(ValueError) as excinfo:
        Settings.from_env()
    assert "MYSQL_PORT cannot be 3306" in str(excinfo.value)


def test_mysql_port_must_be_integer(valid_env, monkeypatch):
    monkeypatch.setenv("MYSQL_PORT", "not-a-port")
    with pytest.raises(ValueError) as excinfo:
        Settings.from_env()
    assert "MYSQL_PORT must be an integer" in str(excinfo.value)


def test_missing_ssl_ca_rejected(valid_env, monkeypatch, tmp_path):
    """A missing CA file must fail validation, not silently downgrade the TLS handshake."""
    monkeypatch.setenv("MYSQL_SSL_CA", str(tmp_path / "does-not-exist.pem"))
    with pytest.raises(ValueError) as excinfo:
        Settings.from_env()
    assert "MYSQL_SSL_CA does not exist on disk" in str(excinfo.value)


def test_empty_ssl_ca_rejected(valid_env, monkeypatch, tmp_path):
    empty = tmp_path / "empty.pem"
    empty.write_text("")
    monkeypatch.setenv("MYSQL_SSL_CA", str(empty))
    with pytest.raises(ValueError) as excinfo:
        Settings.from_env()
    assert "MYSQL_SSL_CA exists but is empty" in str(excinfo.value)


def test_instance_connection_name_shape(valid_env, monkeypatch):
    monkeypatch.setenv("PG_INSTANCE_CONNECTION_NAME", "proj:inst")
    with pytest.raises(ValueError) as excinfo:
        Settings.from_env()
    assert "PROJECT:REGION:INSTANCE" in str(excinfo.value)


def test_local_file_db_target_rejected(valid_env, monkeypatch):
    """This project has no local-file store: a sqlite target anywhere must fail loudly."""
    monkeypatch.setenv("MY_SQLITE_TARGET", "sqlite:///test.db")
    with pytest.raises(ValueError) as excinfo:
        Settings.from_env()
    assert "SQLite target forbidden" in str(excinfo.value)
    monkeypatch.delenv("MY_SQLITE_TARGET")


def test_unrelated_value_containing_db_is_not_rejected(valid_env, monkeypatch):
    """The rejection matches connection targets, not any value that happens to contain '.db'."""
    monkeypatch.setenv("SOME_TOOL_HOME", "C:/tools/.dbeaver/config")
    settings = Settings.from_env()
    assert settings.gcp_project == "proj"
    monkeypatch.delenv("SOME_TOOL_HOME")


def test_region_location_mismatch_rejected(valid_env, monkeypatch):
    """pg_connect_mode direct without pg_host is rejected."""
    monkeypatch.setenv("PG_CONNECT_MODE", "direct")
    monkeypatch.setenv("PG_HOST", "")
    with pytest.raises(ValueError) as excinfo:
        Settings.from_env()
    message = str(excinfo.value)
    assert "PG_HOST is empty" in message


def test_exact_region_is_accepted(valid_env, monkeypatch):
    monkeypatch.setenv("BQ_LOCATION", "europe-west1")
    assert Settings.from_env().bq_location == "europe-west1"


def test_us_region_maps_to_us_multiregion(valid_env, monkeypatch):
    monkeypatch.setenv("PG_INSTANCE_CONNECTION_NAME", "proj:us-central1:inst")
    monkeypatch.setenv("BQ_LOCATION", "US")
    assert Settings.from_env().bq_location == "US"


def test_direct_mode_requires_host(valid_env, monkeypatch):
    monkeypatch.setenv("PG_CONNECT_MODE", "direct")
    with pytest.raises(ValueError) as excinfo:
        Settings.from_env()
    assert "PG_HOST is empty" in str(excinfo.value)


def test_secrets_are_redacted(valid_env):
    rows = dict(Settings.from_env().redacted_rows())
    assert rows["mysql_password"] == "***"
    assert rows["pg_password"] == "***"
    assert rows["pg_bq_reader_password"] == "***"
    assert rows["kaggle_key"] == "***"
    assert rows["mysql_host"] == "host.aivencloud.com"
