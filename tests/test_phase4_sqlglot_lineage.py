"""Unit tests for Phase 4 AST table extraction using sqlglot."""

from pwa.agent.pipeline.exec_agent import _extract_source_tables


def test_simple_table_extraction():
    sql = "SELECT id, name FROM dataset.customers"
    tables = _extract_source_tables(sql)
    assert tables == ["dataset.customers"] or tables == ["customers"]


def test_cte_table_extraction_excludes_cte_aliases():
    sql = """
    WITH regional_sales AS (
        SELECT region, SUM(amount) AS total_sales
        FROM pwa_warehouse.fact_sales_order
        GROUP BY region
    ),
    top_regions AS (
        SELECT region FROM regional_sales WHERE total_sales > 10000
    )
    SELECT * FROM top_regions
    JOIN pwa_warehouse.dim_territory t ON top_regions.region = t.region_name
    """
    tables = _extract_source_tables(sql)
    # Must contain physical base tables fact_sales_order & dim_territory, NOT CTE names regional_sales / top_regions
    assert "regional_sales" not in tables
    assert "top_regions" not in tables
    assert any("fact_sales_order" in t for t in tables)
    assert any("dim_territory" in t for t in tables)


def test_subquery_and_table_aliases():
    sql = "SELECT o.order_id, c.email FROM (SELECT * FROM warehouse.orders) o JOIN warehouse.customers c ON o.cust_id = c.id"
    tables = _extract_source_tables(sql)
    assert any("orders" in t for t in tables)
    assert any("customers" in t for t in tables)
