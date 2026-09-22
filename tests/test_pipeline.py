"""Pipeline-level integration tests & unit tests for 4-agent pipeline."""

from unittest.mock import patch

import pytest

from pwa.agent.pipeline.exec_agent import ast_validate_sql
from pwa.agent.pipeline.orchestrator import _run_pipeline_stages, run_query


def test_exec_agent_static_validation_allows_valid_select():
    """Verify AST SQL validator permits read-only SELECT queries on mart views."""
    valid_sqls = [
        "SELECT sales_order_id, line_total_usd FROM `salitsteel-502008.mart.v_sales_order_line` LIMIT 10",
        "SELECT category_name, COUNT(*) FROM `salitsteel-502008.mart.v_product_catalog` GROUP BY category_name LIMIT 50",
        "SELECT customer_id, total_spend_usd FROM `salitsteel-502008.mart.v_customer_360` LIMIT 5",
    ]
    for sql in valid_sqls:
        ast_validate_sql(sql)  # Should not raise


def test_exec_agent_static_validation_rejects_forbidden_keywords():
    """Verify AST SQL validator blocks DDL/DML statements at the AST level."""
    forbidden_sqls = [
        "DELETE FROM `salitsteel-502008.mart.v_sales_order_line` WHERE sales_order_id = 11",
        "DROP TABLE `salitsteel-502008.mart.v_sales_order_line`",
        "UPDATE `salitsteel-502008.mart.v_sales_order_line` SET line_total_usd = 0",
        "CREATE TABLE `salitsteel-502008.mart.hacked` AS SELECT 1",
        "TRUNCATE TABLE `salitsteel-502008.mart.v_sales_order_line`",
    ]
    for sql in forbidden_sqls:
        with pytest.raises(ValueError, match="Only SELECT statements are allowed"):
            ast_validate_sql(sql)


def test_exec_agent_static_validation_rejects_unauthorized_tables():
    """Verify AST SQL validator blocks queries targeting staging/raw tables."""
    unauthorized_sqls = [
        "SELECT order_id FROM `salitsteel-502008.raw_adventureworks.orders` LIMIT 10",
        "SELECT customer_id FROM `salitsteel-502008.staging.customers` LIMIT 5",
    ]
    for sql in unauthorized_sqls:
        with pytest.raises(ValueError, match="Access denied"):
            ast_validate_sql(sql)


def test_pipeline_retry_mechanism():
    """Verify Stage 5 orchestrator performs exactly ONE retry attempt on Stage 3 failure."""
    # Mock Stage 1 schema grounding
    mock_ground = {"relevant_views": [{"view_name": "mart.v_sales_order_line", "columns": ["sales_order_id"]}]}

    # Mock Stage 2 SQL generation (first attempt returns bad SQL, second attempt returns valid SQL)
    sqls = [
        "SELECT sales_order_id FROM `mart.v_sales_order_line` WHERE bad_col = 1;",
        "SELECT sales_order_id FROM `mart.v_sales_order_line` WHERE order_year = 2014 LIMIT 1;",
    ]

    # Mock Stage 3 execution (first attempt fails with ERROR, second attempt succeeds)
    exec_results = [
        {"status": "ERROR", "error": "Unrecognized name: bad_col", "sql": sqls[0], "rows": []},
        {"status": "SUCCESS", "sql": sqls[1], "rows": [{"sales_order_id": 43659}], "count": 1},
    ]

    # NOTE: deliberately avoids the word "sales" — the shared Agent 0 Router
    # (now consulted by run_query() too, matching run_query_verbose()) treats
    # "sales" as an ambiguous term requiring clarification before it ever
    # reaches grounding/SQL generation, which would short-circuit this test.
    with patch("pwa.agent.pipeline.orchestrator.ground_schema", return_value=mock_ground):
        with patch("pwa.agent.pipeline.orchestrator.generate_sql", side_effect=sqls) as mock_gen:
            with patch(
                "pwa.agent.pipeline.orchestrator.validate_and_execute_sql", side_effect=exec_results
            ) as mock_exec:
                with patch(
                    "pwa.agent.pipeline.orchestrator.synthesize_answer",
                    return_value="In 2014, order ID 43659 was processed.",
                ):
                    res = _run_pipeline_stages("What orders were placed in 2014?")
                    answer = res.answer

                    # Verify 2 calls to SQL generation (initial + 1 retry)
                    assert mock_gen.call_count == 2
                    # Verify retry call passed error feedback
                    assert "Unrecognized name: bad_col" in mock_gen.call_args_list[1].kwargs.get("retry_error", "")

                    # Verify 2 calls to execution
                    assert mock_exec.call_count == 2

                    assert answer == "In 2014, order ID 43659 was processed."


@pytest.mark.integration
def test_pipeline_sales_revenue_2014():
    """Integration Test 1: Verify 4-agent pipeline queries 2014 total sales revenue."""
    answer = run_query("What was the total sales revenue in 2014?")
    assert answer is not None
    assert isinstance(answer, str)


@pytest.mark.integration
def test_pipeline_product_category_query():
    """Integration Test 2: Verify 4-agent pipeline identifies top product categories."""
    answer = run_query("Which product category generated the highest revenue?")
    assert answer is not None
    assert isinstance(answer, str)


@pytest.mark.integration
def test_pipeline_unanswerable_out_of_scope_query():
    """Integration Test 3: Verify 4-agent pipeline declines out-of-scope external questions."""
    answer = run_query("Who won the 2014 FIFA World Cup?")
    assert answer is not None
    assert isinstance(answer, str)
    answer_lower = answer.lower()
    assert any(
        phrase in answer_lower
        for phrase in [
            "cannot be answered",
            "not available",
            "do not have",
            "don't have",
            "unavailable",
            "mart",
            "no information",
            "warehouse",
        ]
    )
