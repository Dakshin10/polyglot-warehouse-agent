"""Integration tests for NLP Query Agent (src/pwa/agent/root_agent.py)."""

import pytest

from pwa.agent.root_agent import run_query


@pytest.mark.integration
def test_highest_revenue_movie_2010():
    """Integration Test 1: Verify agent correctly queries highest revenue movie in 2010."""
    answer = run_query("Which movie had the highest revenue in 2010?")
    assert answer is not None
    assert isinstance(answer, str)
    assert "Toy Story 3" in answer or "1,066,969,703" in answer or "1066969703" in answer


@pytest.mark.integration
def test_director_query():
    """Integration Test 2: Verify agent correctly identifies director of Inception."""
    answer = run_query("Who directed Inception?")
    assert answer is not None
    assert isinstance(answer, str)
    assert "Christopher Nolan" in answer


@pytest.mark.integration
def test_genre_query():
    """Integration Test 3: Verify agent queries genre or ROI information."""
    answer = run_query("List 3 Action movies with their release year and revenue.")
    assert answer is not None
    assert isinstance(answer, str)
    assert len(answer) > 20
    # Should be synthesized natural language rather than raw JSON
    assert not answer.startswith('{"status"')


@pytest.mark.integration
def test_unanswerable_out_of_scope_query():
    """Integration Test 4: Verify agent declines out-of-scope personal/non-movie questions."""
    answer = run_query("What is Christopher Nolan's personal home address and phone number?")
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
            "address",
            "no information",
        ]
    )
