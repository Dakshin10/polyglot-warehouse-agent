"""Unit tests for ADK BigQueryToolset module (src/pwa/agent/bq_tools.py)."""

from unittest.mock import MagicMock

import pytest

try:
    from google.adk.integrations.bigquery.config import WriteMode
except ImportError:
    from google.adk.tools.bigquery.config import WriteMode

from pwa.agent.bq_tools import (
    ALLOWED_MART_VIEWS,
    get_mart_credentials_config,
    get_mart_tool_config,
    get_mart_toolset,
    schema_snapshot,
    validate_mart_table,
)


def test_write_mode_is_blocked():
    """Requirement 2 & 6: Verify write_mode is strictly WriteMode.BLOCKED."""
    tool_config = get_mart_tool_config()
    assert tool_config.write_mode == WriteMode.BLOCKED
    assert tool_config.write_mode.value == "blocked"

    toolset = get_mart_toolset()
    assert toolset._tool_settings.write_mode == WriteMode.BLOCKED


def test_allowlist_validation_accepts_valid_mart_views():
    """Requirement 3 & 6: Verify allowlist validation accepts all 5 mart views."""
    for view in ALLOWED_MART_VIEWS:
        assert validate_mart_table(view) == view.lower()
        # Test with backticks and uppercase
        assert validate_mart_table(f"`{view.upper()}`") == view.lower()
        # Test with project prefix
        assert validate_mart_table(f"salitsteel-502008.{view}") == view.lower()


def test_allowlist_validation_rejects_non_mart_tables():
    """Requirement 3 & 6: Verify allowlist validation rejects non-mart tables and invalid inputs."""
    invalid_tables = [
        "raw_registry.movie",
        "raw_credits.movie_credits",
        "raw_files.movie_keywords",
        "staging_movies",
        "mart.v_unknown_view",
        "public.movie",
        "select * from mart.v_movie",
    ]
    for invalid in invalid_tables:
        with pytest.raises(ValueError, match="Access denied"):
            validate_mart_table(invalid)

    with pytest.raises(ValueError, match="Table name cannot be empty"):
        validate_mart_table("")


def test_schema_snapshot_with_mocked_client():
    """Requirement 4 & 6: Verify schema_snapshot returns expected column metadata."""
    mock_client = MagicMock()
    mock_query_job = MagicMock()

    # Create mock rows representing INFORMATION_SCHEMA results
    Row1 = MagicMock(table_name="v_movie", column_name="movie_id", data_type="INTEGER", description="Unique movie ID")
    Row2 = MagicMock(table_name="v_movie", column_name="title", data_type="STRING", description="Movie title")
    Row3 = MagicMock(
        table_name="v_movie_credits", column_name="director_name", data_type="STRING", description="Director name"
    )

    mock_query_job.result.return_value = [Row1, Row2, Row3]
    mock_client.query.return_value = mock_query_job

    snapshot = schema_snapshot(mock_client)

    # Verify query was called
    assert mock_client.query.called
    query_str = mock_client.query.call_args[0][0]
    assert "INFORMATION_SCHEMA.COLUMNS" in query_str
    assert "v_movie" in query_str

    # Verify snapshot contents
    assert "mart.v_movie" in snapshot
    assert "mart.v_movie_credits" in snapshot
    assert "mart.v_movie_keywords" in snapshot

    # Verify column fields
    v_movie_cols = snapshot["mart.v_movie"]
    assert len(v_movie_cols) == 2
    assert v_movie_cols[0] == {"name": "movie_id", "type": "INTEGER", "description": "Unique movie ID"}
    assert v_movie_cols[1] == {"name": "title", "type": "STRING", "description": "Movie title"}

    v_credits_cols = snapshot["mart.v_movie_credits"]
    assert len(v_credits_cols) == 1
    assert v_credits_cols[0] == {"name": "director_name", "type": "STRING", "description": "Director name"}


def test_credentials_config():
    """Requirement 1: Verify get_mart_credentials_config builds a valid ADK credentials config."""
    config = get_mart_credentials_config()
    assert config is not None
    assert hasattr(config, "credentials")
