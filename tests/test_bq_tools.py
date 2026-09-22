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
        "raw_adventureworks.orders",
        "raw_olist.orders",
        "staging_enterprise",
        "mart.v_unknown_view",
        "public.orders",
        "select * from mart.v_sales_order_line",
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
    Row1 = MagicMock(
        table_name="v_sales_order_line",
        column_name="sales_order_id",
        data_type="INTEGER",
        description="Unique order ID",
    )
    Row2 = MagicMock(
        table_name="v_sales_order_line", column_name="line_total_usd", data_type="FLOAT", description="Line item total"
    )
    Row3 = MagicMock(
        table_name="v_product_catalog", column_name="product_name", data_type="STRING", description="Product name"
    )

    mock_query_job.result.return_value = [Row1, Row2, Row3]
    mock_client.query.return_value = mock_query_job

    snapshot = schema_snapshot(mock_client)

    # Verify query was called
    assert mock_client.query.called
    query_str = mock_client.query.call_args[0][0]
    assert "INFORMATION_SCHEMA.COLUMNS" in query_str
    assert "v_sales_order_line" in query_str

    # Verify snapshot contents
    assert "mart.v_sales_order_line" in snapshot
    assert "mart.v_product_catalog" in snapshot
    assert "mart.v_customer_360" in snapshot

    # Verify column fields
    v_sales_cols = snapshot["mart.v_sales_order_line"]
    assert len(v_sales_cols) == 2
    assert v_sales_cols[0] == {"name": "sales_order_id", "type": "INTEGER", "description": "Unique order ID"}
    assert v_sales_cols[1] == {"name": "line_total_usd", "type": "FLOAT", "description": "Line item total"}

    v_prod_cols = snapshot["mart.v_product_catalog"]
    assert len(v_prod_cols) == 1
    assert v_prod_cols[0] == {"name": "product_name", "type": "STRING", "description": "Product name"}


def test_credentials_config():
    """Requirement 1: Verify get_mart_credentials_config builds a valid ADK credentials config."""
    config = get_mart_credentials_config()
    assert config is not None
    assert hasattr(config, "credentials")
