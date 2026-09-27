"""Regression test suite for grain-aware fan-out detection and CTE pre-aggregation."""

import sqlite3
import pytest
import pandas as pd

from pwa.agent.errors import SemanticGrainValidationError
from pwa.semantic.loader import get_semantic_catalog
from pwa.semantic.query_planner import AnalyticalIntent, QueryPlanner
from pwa.semantic.sql_generator import GovernedSqlGenerator


def test_strict_grain_validation_blocks_fanout():
    """Task 1: Assert strict grain validation raises SemanticGrainValidationError on multi-grain fan-out risk."""
    catalog = get_semantic_catalog()
    planner = QueryPlanner(catalog)

    # Intent combining header measure (revenue) and detail measure (quantity_sold)
    intent = AnalyticalIntent(
        entities=["fact_sales_order", "fact_sales_order_item"],
        measures=["revenue", "quantity_sold"],
    )

    with pytest.raises(SemanticGrainValidationError) as exc_info:
        planner.plan_query(intent, strict_grain_validation=True)

    err = exc_info.value
    assert "Grain validation error" in str(err)
    assert len(err.fanout_details) > 0
    assert err.fanout_details[0]["relationship"] == "sales_order_to_item"


def test_same_grain_query_compiles_without_cte():
    """Task 2a: Assert queries with measures from the same grain compile standard SQL without CTE pre-aggregation overhead."""
    catalog = get_semantic_catalog()
    planner = QueryPlanner(catalog)
    generator = GovernedSqlGenerator()

    intent = AnalyticalIntent(
        entities=["fact_sales_order"],
        measures=["revenue"],
    )

    plan = planner.plan_query(intent)
    assert plan.fanout_risk is False
    assert len(plan.fanout_details) == 0

    sql = generator.compile_sql(plan)
    assert "WITH " not in sql
    assert "fact_sales_order_agg" not in sql
    assert "FROM `curated_enterprise.fact_sales_order`" in sql


def test_multi_grain_query_cte_preaggregation_numerical_correctness():
    """Task 2b & 2c: Assert pre-aggregated CTE SQL resolves the reproduction case to $100.00 instead of $300.00."""
    catalog = get_semantic_catalog()
    planner = QueryPlanner(catalog)
    generator = GovernedSqlGenerator()

    intent = AnalyticalIntent(
        entities=["fact_sales_order", "fact_sales_order_item"],
        measures=["revenue", "quantity_sold"],
    )

    plan = planner.plan_query(intent, strict_grain_validation=False)
    assert plan.fanout_risk is True
    assert len(plan.fanout_details) > 0

    sql = generator.compile_sql(plan)
    assert "WITH " in sql
    assert "fact_sales_order_agg AS (" in sql
    assert "fact_sales_order_item_agg AS (" in sql

    # Execute generated CTE SQL against SQLite containing the reproduction dataset
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE fact_sales_order (
        sales_order_id INT,
        total_due REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE fact_sales_order_item (
        sales_order_id INT,
        order_qty INT
    )
    """)

    # 1 order header ($100.00)
    cursor.execute("INSERT INTO fact_sales_order VALUES (1, 100.0)")

    # 3 detail line items (qty: 2, 5, 3 => sum = 10)
    cursor.execute("INSERT INTO fact_sales_order_item VALUES (1, 2)")
    cursor.execute("INSERT INTO fact_sales_order_item VALUES (1, 5)")
    cursor.execute("INSERT INTO fact_sales_order_item VALUES (1, 3)")
    conn.commit()

    # Clean backticks from BigQuery table names so query executes on SQLite memory tables
    sqlite_sql = sql.replace("`curated_enterprise.fact_sales_order`", "fact_sales_order").replace(
        "`curated_enterprise.fact_sales_order_item`", "fact_sales_order_item"
    )

    df = pd.read_sql_query(sqlite_sql, conn)

    assert len(df) == 1
    assert df["revenue"].iloc[0] == 100.0, f"Revenue should be $100.00, got {df['revenue'].iloc[0]}"
    assert df["quantity_sold"].iloc[0] == 10, f"Quantity sold should be 10, got {df['quantity_sold'].iloc[0]}"
