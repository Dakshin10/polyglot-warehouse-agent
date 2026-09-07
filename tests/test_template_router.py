"""Unit tests for Intent and Template Router fast-path routing."""

from pwa.agent.template_router import match_template, parse_revenue_threshold, parse_top_n


def test_parse_revenue_threshold():
    """Verify parsing of revenue threshold strings."""
    assert parse_revenue_threshold("movies with over 500M revenue") == 500_000_000
    assert parse_revenue_threshold("movies over $500 million revenue") == 500_000_000
    assert parse_revenue_threshold("movies above 100M USD") == 100_000_000
    assert parse_revenue_threshold("movies over $1 billion") == 1_000_000_000


def test_parse_top_n():
    """Verify parsing of top N limits."""
    assert parse_top_n("top 5 highest-grossing movies") == 5
    assert parse_top_n("top 10 grossing films") == 10
    assert parse_top_n("highest grossing movies", default=5) == 5


def test_match_template_avg_roi_director():
    """Verify matching for director average ROI queries."""
    q = "Which director has the highest average ROI across their movies?"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "avg_roi_by_director"
    assert match["table_name"] == "rollup.avg_roi_by_director"


def test_match_template_avg_cast_size():
    """Verify matching for average cast size threshold queries."""
    q = "What is the average cast size for movies with over 500M revenue?"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "avg_cast_size_by_revenue_threshold"
    assert match["params"]["threshold"] == 500_000_000


def test_match_template_top_grossing():
    """Verify matching for top grossing movies queries."""
    q = "Top 5 highest-grossing movies"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "top_grossing_movies"
    assert match["params"]["limit"] == 5


def test_match_template_novel_fallthrough():
    """Verify novel question returns None to trigger LLM pipeline fallthrough."""
    q = "Which movies feature keywords related to space travel?"
    match = match_template(q)
    assert match is None
