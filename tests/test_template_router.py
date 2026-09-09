"""Unit tests for Intent and Template Router fast-path routing."""

import pandas as pd

from pwa.agent.template_router import match_template, parse_revenue_threshold, parse_top_n
from pwa.ui.viz_router import choose_visualization


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


def test_match_template_temporal_queries_fallthrough_all_templates():
    """Verify ALL rollup templates fall through to LLM pipeline when a temporal qualifier is present."""
    temporal_questions = [
        "top grossing movies this decade",
        "highest revenue movie since 2015",
        "top 5 movies released last year",
        "highest revenue movie in 2010",
        "highest average ROI director this decade",
        "average ROI by director since 2015",
        "average cast size for movies over $500M released last year",
        "average ROI by genre since 2015",
    ]
    for q in temporal_questions:
        assert match_template(q) is None, f"Query '{q}' should fall through to LLM, but matched a template"


def test_match_template_retains_fast_path_for_non_temporal_phrases():
    """Verify non-temporal phrases like 'from Pixar' or 'between 2 franchises' retain the fast path."""
    q1 = "top grossing movies from Pixar"
    res1 = match_template(q1)
    assert res1 is not None and res1["template_name"] == "top_grossing_movies"

    q2 = "top 5 highest grossing movies between 2 franchises"
    res2 = match_template(q2)
    assert res2 is not None and res2["template_name"] == "top_grossing_movies"


# ── avg_roi_by_genre: new cross-engine template ───────────────────────────────


def test_match_template_avg_roi_by_genre_canonical():
    """Primary phrasing: 'average ROI by genre'."""
    q = "What is the average ROI by genre?"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "avg_roi_by_genre"
    assert match["table_name"] == "rollup.avg_roi_by_genre"


def test_match_template_avg_roi_by_genre_alt_phrasing():
    """Alternative phrasing: 'which genre is most profitable'."""
    q = "Which genre is the most profitable on average?"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "avg_roi_by_genre"


def test_match_template_avg_roi_by_genre_per_genre():
    """'Average return per genre' phrasing."""
    q = "What is the average return on investment per genre?"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "avg_roi_by_genre"


def test_match_template_avg_roi_by_genre_performance():
    """'Genre performance' phrasing."""
    q = "Show me genre performance by average ROI"
    match = match_template(q)
    assert match is not None
    assert match["template_name"] == "avg_roi_by_genre"


def test_avg_roi_by_genre_viz_router_gives_bar():
    """The genre breakdown result (1 cat + 1 numeric, 8-15 rows) must route to bar."""
    genres = ["Action", "Drama", "Comedy", "Horror", "Romance", "Thriller", "Animation", "Documentary"]
    df = pd.DataFrame(
        {
            "primary_genre": genres,
            "avg_roi": [3.1, 2.4, 2.8, 4.0, 1.9, 3.5, 5.2, 1.2],
            "avg_revenue_usd": [2e8, 1.5e8, 1.2e8, 0.8e8, 0.9e8, 1.8e8, 3e8, 0.5e8],
            "avg_budget_usd": [6e7, 5e7, 4e7, 2e7, 3e7, 5e7, 4e7, 1e7],
            "movie_count": [450, 600, 550, 300, 350, 400, 200, 150],
        }
    )
    # viz_router should pick avg_roi as y (first numeric col that isn't a datetime/year)
    viz = choose_visualization(df, "average ROI by genre")
    assert viz["type"] == "bar"
    assert viz["x"] == "primary_genre"
    # The first non-datetime numeric column is avg_roi
    assert viz["y"] == "avg_roi"


def test_avg_roi_by_genre_sql_generator():
    """SQL generator produces a valid SELECT against the rollup table."""
    match = match_template("What is the average ROI by genre?")
    assert match is not None
    sql = match["sql_generator"]("my-project", match["params"])
    assert "rollup.avg_roi_by_genre" in sql
    assert "primary_genre" in sql
    assert "avg_roi" in sql


def test_avg_roi_by_genre_formatter_with_rows():
    """Formatter produces a human-readable genre ROI breakdown."""
    match = match_template("What is the average ROI by genre?")
    assert match is not None
    rows = [
        {"primary_genre": "Animation", "avg_roi": 5.2, "avg_revenue_usd": 3e8, "movie_count": 200},
        {"primary_genre": "Action", "avg_roi": 3.1, "avg_revenue_usd": 2e8, "movie_count": 450},
    ]
    answer = match["formatter"](rows, match["params"])
    assert "Animation" in answer
    assert "5.20" in answer
    assert "genre" in answer.lower()


def test_avg_roi_by_genre_formatter_empty():
    """Formatter handles empty rows gracefully."""
    match = match_template("average ROI by genre")
    assert match is not None
    answer = match["formatter"]([], match["params"])
    assert "No genre ROI data" in answer


# ─── Viz Recommendation tests for template match questions ────────────────────


def test_template_match_viz_recommendations():
    """Verify viz recommendation types for the 3 core template-match questions."""
    from pwa.ui.viz_recommendation import build_from_shape

    # 1. highest average ROI director -> 1 row -> metric
    df_dir = pd.DataFrame([{"director_name": "Steven Spielberg", "avg_roi": 5.4, "movie_count": 27}])
    rec_dir = build_from_shape(df_dir, "highest average ROI director")
    assert rec_dir.primary.type == "metric"
    assert rec_dir.primary.y_col == "avg_roi"

    # 2. average cast size for movies over $500M -> 1 row -> metric
    df_cast = pd.DataFrame([{"revenue_threshold": 500_000_000, "avg_cast_size": 42.7, "movie_count": 15}])
    rec_cast = build_from_shape(df_cast, "average cast size for movies over $500M")
    assert rec_cast.primary.type == "metric"
    assert rec_cast.primary.y_col == "avg_cast_size"

    # 3. top 5 highest-grossing movies -> 5 rows -> bar
    df_top5 = pd.DataFrame(
        [
            {"rank": i, "title": f"Movie {i}", "revenue": (6 - i) * 1e8, "director_name": f"Director {i}"}
            for i in range(1, 6)
        ]
    )
    rec_top5 = build_from_shape(df_top5, "top 5 highest-grossing movies")
    assert rec_top5.primary.type == "bar"
    assert rec_top5.primary.x_col == "title"
    assert rec_top5.primary.y_col == "revenue"
