"""Unit tests for AST-based SQL validation (Task P0-1).

Tests confirm that sqlglot AST-based allowlisting catches all attack vectors that the
old keyword-blocklist missed (write ops inside CTEs, malformed SQL, etc.) while still
passing valid SELECTs including EXTERNAL_QUERY federated patterns.

All tests are fully offline — no BigQuery or LLM calls are made.
"""

import pytest

from pwa.agent.pipeline.exec_agent import ast_validate_sql


# ---------------------------------------------------------------------------
# Valid SELECTs — must all PASS
# ---------------------------------------------------------------------------


class TestValidSelects:
    def test_simple_select_passes(self):
        sql = "SELECT sales_order_id, line_total_usd FROM `salitsteel-502008.mart.v_sales_order_line` LIMIT 10"
        ast_validate_sql(sql)  # Should not raise

    def test_select_with_where_passes(self):
        sql = "SELECT sales_order_id, order_date FROM `salitsteel-502008.mart.v_sales_order_line` WHERE order_year = 2014 LIMIT 5"
        ast_validate_sql(sql)

    def test_select_with_join_passes(self):
        sql = (
            "SELECT o.sales_order_id, p.product_name "
            "FROM `salitsteel-502008.mart.v_sales_order_line` o "
            "JOIN `salitsteel-502008.mart.v_product_catalog` p ON o.product_id = p.product_id "
            "LIMIT 10"
        )
        ast_validate_sql(sql)

    def test_aggregate_select_passes(self):
        sql = (
            "SELECT category_name, COUNT(*) AS cnt, ROUND(AVG(list_price_usd), 2) AS avg_price "
            "FROM `salitsteel-502008.mart.v_product_catalog` "
            "GROUP BY category_name ORDER BY cnt DESC LIMIT 5"
        )
        ast_validate_sql(sql)

    def test_external_query_federated_select_passes(self):
        """EXTERNAL_QUERY federated patterns must survive AST validation."""
        sql = (
            "SELECT * FROM EXTERNAL_QUERY("
            "'salitsteel-502008.EU.olist-conn', "
            "'SELECT order_id, payment_value FROM orders LIMIT 10')"
        )
        ast_validate_sql(sql)

    def test_cte_select_passes(self):
        sql = (
            "WITH top_sales AS ("
            "  SELECT sales_order_id, product_id, line_total_usd "
            "  FROM `salitsteel-502008.mart.v_sales_order_line` "
            "  ORDER BY line_total_usd DESC LIMIT 10"
            ") "
            "SELECT t.sales_order_id, p.product_name "
            "FROM top_sales t "
            "JOIN `salitsteel-502008.mart.v_product_catalog` p ON t.product_id = p.product_id"
        )
        ast_validate_sql(sql)

    def test_subquery_select_passes(self):
        sql = (
            "SELECT sales_order_id FROM ("
            "  SELECT sales_order_id, line_total_usd FROM `salitsteel-502008.mart.v_sales_order_line`"
            ") sub ORDER BY line_total_usd DESC LIMIT 3"
        )
        ast_validate_sql(sql)


# ---------------------------------------------------------------------------
# Forbidden top-level statements — must all RAISE ValueError
# ---------------------------------------------------------------------------


class TestTopLevelForbiddenStatements:
    def test_drop_table_rejected(self):
        sql = "DROP TABLE `salitsteel-502008.mart.v_sales_order_line`"
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)

    def test_delete_rejected(self):
        sql = "DELETE FROM `salitsteel-502008.mart.v_sales_order_line` WHERE 1=1"
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)

    def test_update_rejected(self):
        sql = "UPDATE `salitsteel-502008.mart.v_sales_order_line` SET line_total_usd = 0 WHERE sales_order_id = 1"
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)

    def test_insert_rejected(self):
        sql = "INSERT INTO `salitsteel-502008.mart.v_sales_order_line` (sales_order_id) VALUES (999)"
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)

    def test_create_table_rejected(self):
        sql = "CREATE TABLE `salitsteel-502008.mart.exfil` AS SELECT * FROM `salitsteel-502008.mart.v_sales_order_line`"
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)

    def test_truncate_rejected(self):
        sql = "TRUNCATE TABLE `salitsteel-502008.mart.v_sales_order_line`"
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)


# ---------------------------------------------------------------------------
# Write ops HIDDEN inside CTEs — the keyword-blocklist would have missed these
# ---------------------------------------------------------------------------


class TestWriteHiddenInCTE:
    def test_delete_inside_cte_rejected(self):
        """A DELETE smuggled inside a CTE must be rejected by the AST walker."""
        sql = "WITH evil AS (  DELETE FROM `salitsteel-502008.mart.v_sales_order_line` WHERE 1=1) SELECT 1"
        with pytest.raises(ValueError):
            ast_validate_sql(sql)

    def test_insert_inside_cte_rejected(self):
        sql = "WITH evil AS (  INSERT INTO `salitsteel-502008.mart.v_sales_order_line` (sales_order_id) VALUES (1)) SELECT 1"
        with pytest.raises(ValueError):
            ast_validate_sql(sql)

    def test_drop_inside_subquery_rejected(self):
        """Demonstrates AST catch of DROP nested in a sub-expression."""
        sql = "SELECT (DROP TABLE `salitsteel-502008.mart.v_sales_order_line`)"
        with pytest.raises(ValueError):
            ast_validate_sql(sql)


# ---------------------------------------------------------------------------
# Malformed / unparseable SQL — must raise ValueError
# ---------------------------------------------------------------------------


class TestMalformedSQL:
    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ast_validate_sql("")

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ast_validate_sql("   ")

    def test_garbage_string_rejected(self):
        with pytest.raises(ValueError):
            ast_validate_sql("NOT VALID SQL AT ALL ;;; ???")

    def test_semicolon_only_rejected(self):
        with pytest.raises(ValueError):
            ast_validate_sql(";")

    def test_partial_select_rejected(self):
        with pytest.raises(ValueError):
            ast_validate_sql("SELECT FROM")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_select_with_comment_passes(self):
        """SQL with comments must still parse and pass."""
        sql = "-- get sales\nSELECT sales_order_id, line_total_usd FROM `salitsteel-502008.mart.v_sales_order_line` LIMIT 5"
        ast_validate_sql(sql)

    def test_backtick_wrapped_sql_passes(self):
        sql = "SELECT `sales_order_id` FROM `salitsteel-502008.mart.v_sales_order_line` LIMIT 1"
        ast_validate_sql(sql)

    def test_select_1_passes(self):
        """Connectivity-check query must pass."""
        ast_validate_sql("SELECT 1")
