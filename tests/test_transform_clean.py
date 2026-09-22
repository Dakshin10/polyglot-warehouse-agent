"""Unit tests for enterprise dataset ingestion & staging utilities."""

import pandas as pd
from pwa.source_registry import SourceTableConfig, SourceConfig


def test_source_config_properties():
    """Verify SourceConfig typed properties and table lookup."""
    tbl = SourceTableConfig(name="orders", source_file_pattern="orders.csv", primary_key="order_id")
    cfg = SourceConfig(
        name="olist",
        type="file",
        provider="kaggle",
        slug="olistbr/brazilian-ecommerce",
        source_url="https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce",
        domain="marketplace",
        description="Olist E-Commerce",
        ingestion_mode="snapshot",
        local_path="data/source/olist/",
        bq_raw_dataset="raw_olist",
        license="CC BY-NC-SA 4.0",
        tables=[tbl],
    )

    assert cfg.name == "olist"
    assert cfg.table_names == ["orders"]
    assert cfg.get_table("orders") == tbl
    assert cfg.get_table("non_existent") is None


def test_dataframe_currency_formatting():
    """Verify numeric coercion and total calculation on sales data."""
    df = pd.DataFrame(
        [
            {"order_id": 1, "line_total": "100.50"},
            {"order_id": 2, "line_total": "250.00"},
            {"order_id": 3, "line_total": "invalid"},
        ]
    )

    df["line_total_usd"] = pd.to_numeric(df["line_total"], errors="coerce").fillna(0.0)
    assert df["line_total_usd"].sum() == 350.50
    assert len(df) == 3
