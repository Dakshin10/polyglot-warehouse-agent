"""Unit tests for Intent and Template Router fast-path routing — Enterprise Domain."""

import pandas as pd

from pwa.agent.template_router import match_template, parse_top_n
from pwa.ui.viz_router import choose_visualization


def test_parse_top_n():
    """Verify parsing of limit N limits."""
    assert parse_top_n("top 5 categories by sales") == 5
    assert parse_top_n("top 10 suppliers") == 10
    assert parse_top_n("top categories", default=5) == 5


def test_match_template_sales_by_year():
    """Verify matching for annual sales revenue queries."""
    q = "What was the total sales revenue by year?"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "sales_by_year"
    assert match["table_name"] == "rollup.sales_by_year"


def test_match_template_product_sales_by_category():
    """Verify matching for product sales by category queries."""
    q = "Which product category generated the highest revenue?"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "product_sales_by_category"
    assert match["table_name"] == "rollup.product_sales_by_category"


def test_match_template_supplier_purchase_volume():
    """Verify matching for supplier purchase volume queries."""
    q = "What is the total purchase volume by supplier vendor?"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "supplier_purchase_volume"


def test_match_template_customer_order_distribution():
    """Verify matching for customer order distribution queries."""
    q = "What is the distribution of orders per customer?"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "customer_order_distribution"


def test_match_template_employee_department_headcount():
    """Verify matching for employee headcount by department queries."""
    q = "What is the employee headcount by department?"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "employee_department_headcount"


def test_match_template_marketplace_monthly_sales():
    """Verify matching for marketplace monthly sales queries."""
    q = "What are the monthly sales trends on the Olist marketplace?"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "marketplace_monthly_sales"


def test_match_template_marketplace_review_ratings():
    """Verify matching for marketplace review rating distribution queries."""
    q = "What is the distribution of review star ratings on the marketplace?"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "marketplace_review_ratings"


def test_match_template_novel_fallthrough():
    """Verify out-of-scope/novel question returns None to trigger LLM pipeline fallthrough."""
    q = "Which movies feature space travel?"
    match = match_template(q)
    assert match is None


def test_sales_by_year_viz_router_gives_line_or_bar():
    """Verify visualization choice for sales by year dataset."""
    df = pd.DataFrame(
        {
            "order_year": [2011, 2012, 2013, 2014],
            "total_sales_usd": [1200000.0, 3400000.0, 4800000.0, 5100000.0],
            "order_count": [500, 1200, 1800, 2100],
        }
    )
    viz = choose_visualization(df, "total sales revenue by year")
    assert viz["type"] in ("bar", "line")
    assert viz["x"] == "order_year"


def test_template_match_sql_generator():
    """SQL generator produces a valid SELECT against the rollup table."""
    match = match_template("What was the total sales revenue by year?")
    assert match is not None
    sql = match["sql_generator"]("my-project", match["params"])
    assert "rollup.sales_by_year" in sql
    assert "total_sales_usd" in sql


def test_template_match_formatter_with_rows():
    """Formatter produces a human-readable summary for sales by year."""
    match = match_template("What was the total sales revenue by year?")
    assert match is not None
    rows = [
        {"order_year": 2013, "total_sales_usd": 4800000.0, "order_count": 1800},
        {"order_year": 2014, "total_sales_usd": 5100000.0, "order_count": 2100},
    ]
    answer = match["formatter"](rows, match["params"])
    assert "2013" in answer
    assert "4,800,000" in answer or "4800000" in answer
