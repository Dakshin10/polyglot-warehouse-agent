"""Unit tests for shape-based visualization router (no LLM, no BigQuery)."""

import pandas as pd

from pwa.ui.viz_router import choose_visualization


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _df(*records, **col_overrides):
    """Build a small DataFrame from a list of dicts."""
    return pd.DataFrame(records)


# ──────────────────────────────────────────────────────────────────────────────
# metric cases
# ──────────────────────────────────────────────────────────────────────────────


class TestMetric:
    def test_single_row_two_cols_gives_metric(self):
        """highest average ROI director → 1 row, director + roi columns."""
        df = _df({"director_name": "Christopher Nolan", "avg_roi": 4.23})
        result = choose_visualization(df, "Which director has the highest average ROI?")
        assert result["type"] == "metric"
        assert result["y"] == "avg_roi"

    def test_single_row_one_col_gives_metric(self):
        """average cast size for movies over $500M → 1 row, 1 numeric column."""
        df = _df({"avg_cast_size": 42.7})
        result = choose_visualization(df, "What is the average cast size for movies over $500M?")
        assert result["type"] == "metric"
        assert result["y"] == "avg_cast_size"

    def test_single_row_two_numeric_cols_gives_metric(self):
        """1 row, 2 numeric columns stays metric (≤2 cols rule)."""
        df = _df({"avg_budget": 150_000_000, "avg_revenue": 400_000_000})
        result = choose_visualization(df, "average budget and revenue")
        assert result["type"] == "metric"


# ──────────────────────────────────────────────────────────────────────────────
# table cases
# ──────────────────────────────────────────────────────────────────────────────


class TestTable:
    def test_more_than_20_rows_always_table(self):
        """21 rows → table regardless of column count."""
        df = pd.DataFrame({"title": [f"Movie {i}" for i in range(21)], "revenue": range(21)})
        result = choose_visualization(df, "all movies by revenue")
        assert result["type"] == "table"

    def test_exactly_21_rows_table(self):
        df = pd.DataFrame({"genre": [f"g{i}" for i in range(21)], "count": range(21)})
        result = choose_visualization(df, "movies per genre")
        assert result["type"] == "table"

    def test_multiple_categorical_cols_table(self):
        """3 categorical columns → no clean x/y pair → table."""
        df = pd.DataFrame({"director": ["A", "B"], "genre": ["Action", "Drama"], "studio": ["X", "Y"]})
        result = choose_visualization(df, "directors and genres by studio")
        assert result["type"] == "table"

    def test_three_numeric_cols_table(self):
        """3 numeric columns (no clean single y) → table."""
        df = pd.DataFrame({"budget": [100, 200], "revenue": [300, 400], "profit": [200, 200]})
        result = choose_visualization(df, "budget revenue profit breakdown")
        assert result["type"] == "table"

    def test_empty_dataframe_table(self):
        df = pd.DataFrame()
        result = choose_visualization(df, "anything")
        assert result["type"] == "table"


# ──────────────────────────────────────────────────────────────────────────────
# bar cases
# ──────────────────────────────────────────────────────────────────────────────


class TestBar:
    def test_top5_movies_by_revenue_gives_bar(self):
        """top 5 highest-grossing movies → title (cat) + revenue (num), 5 rows."""
        rows = [{"title": f"Movie {i}", "revenue": (5 - i) * 1_000_000} for i in range(5)]
        df = pd.DataFrame(rows)
        result = choose_visualization(df, "top 5 highest-grossing movies")
        assert result["type"] == "bar"
        assert result["x"] == "title"
        assert result["y"] == "revenue"

    def test_genre_breakdown_gives_bar(self):
        """average ROI by genre (e.g. 8 genres) → bar."""
        df = pd.DataFrame({"genre": ["Action", "Drama", "Comedy", "Horror"], "avg_roi": [3.1, 2.4, 2.8, 4.0]})
        result = choose_visualization(df, "average ROI by genre")
        assert result["type"] == "bar"
        assert result["x"] == "genre"
        assert result["y"] == "avg_roi"

    def test_exactly_20_rows_still_bar(self):
        """20 rows is the boundary — still eligible for bar."""
        df = pd.DataFrame({"cat": [f"c{i}" for i in range(20)], "val": range(20)})
        result = choose_visualization(df, "values by category")
        assert result["type"] == "bar"

    def test_x_and_y_cols_are_set(self):
        df = pd.DataFrame({"director": ["Nolan", "Spielberg", "Tarantino"], "movies": [12, 30, 10]})
        result = choose_visualization(df, "movies per director")
        assert result["x"] == "director"
        assert result["y"] == "movies"


# ──────────────────────────────────────────────────────────────────────────────
# line cases
# ──────────────────────────────────────────────────────────────────────────────


class TestLine:
    def test_year_column_plus_numeric_gives_line(self):
        """year (integer col named 'year') + revenue → line."""
        df = pd.DataFrame({"year": [2018, 2019, 2020, 2021], "revenue": [1e9, 1.2e9, 0.9e9, 1.5e9]})
        result = choose_visualization(df, "revenue by year")
        assert result["type"] == "line"
        assert result["x"] == "year"
        assert result["y"] == "revenue"

    def test_trend_keyword_upgrades_to_line(self):
        """'trend' in question upgrades categorical+numeric pair to line."""
        df = pd.DataFrame({"period": ["Q1", "Q2", "Q3", "Q4"], "sales": [100, 120, 110, 130]})
        result = choose_visualization(df, "sales trend over time")
        assert result["type"] == "line"

    def test_over_time_keyword_upgrades_to_line(self):
        df = pd.DataFrame({"quarter": ["Q1", "Q2", "Q3", "Q4"], "revenue": [10, 20, 15, 25]})
        result = choose_visualization(df, "revenue over time by quarter")
        assert result["type"] == "line"

    def test_by_year_keyword_upgrades_to_line(self):
        df = pd.DataFrame({"release_year": ["2019", "2020", "2021", "2022"], "count": [5, 7, 4, 9]})
        result = choose_visualization(df, "movies released by year")
        # release_year strings look like YYYY → datetime col
        assert result["type"] == "line"

    def test_datetime_dtype_column_gives_line(self):
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2022-01", "2022-02", "2022-03", "2022-04"]),
                "revenue": [100, 200, 150, 250],
            }
        )
        result = choose_visualization(df, "monthly revenue")
        assert result["type"] == "line"
        assert result["x"] == "date"


# ──────────────────────────────────────────────────────────────────────────────
# x / y invariants
# ──────────────────────────────────────────────────────────────────────────────


class TestColumnInvariants:
    def test_metric_has_no_x(self):
        df = _df({"score": 99.5})
        result = choose_visualization(df, "top score")
        assert result["x"] is None

    def test_bar_x_is_categorical_col(self):
        df = pd.DataFrame({"country": ["US", "UK", "FR"], "count": [10, 5, 7]})
        result = choose_visualization(df, "count by country")
        assert result["type"] == "bar"
        assert result["x"] == "country"
        assert result["y"] == "count"
