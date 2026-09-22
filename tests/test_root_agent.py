"""Integration tests for NLP Query Agent (src/pwa/agent/root_agent.py)."""

import pytest

from pwa.agent.root_agent import run_query


@pytest.mark.integration
def test_sales_revenue_2014():
    """Integration Test 1: Verify agent correctly queries total sales revenue in 2014."""
    answer = run_query("What was the total sales revenue in 2014?")
    assert answer is not None
    assert isinstance(answer, str)


@pytest.mark.integration
def test_product_category_query():
    """Integration Test 2: Verify agent correctly identifies top product categories."""
    answer = run_query("Which product category generated the highest sales revenue?")
    assert answer is not None
    assert isinstance(answer, str)


@pytest.mark.integration
def test_unanswerable_out_of_scope_query():
    """Integration Test 3: Verify agent declines out-of-scope non-warehouse questions."""
    answer = run_query("Who won the 2014 FIFA World Cup?")
    assert answer is not None
    assert isinstance(answer, str)
    answer_lower = answer.lower()
    # Agent should state that this information is not available in the mart views
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
            "scope",
        ]
    )
