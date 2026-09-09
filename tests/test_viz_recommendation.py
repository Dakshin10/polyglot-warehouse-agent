"""Unit tests for VizSpec / VizRecommendation schema + fast-path builder.

All tests are pure-Python: no Streamlit, no BigQuery, no LLM calls.
"""

import json

import pandas as pd
import pytest

from pwa.ui.viz_recommendation import (
    VizRecommendation,
    VizSpec,
    VALID_TYPES,
    build_from_llm_dict,
    build_from_shape,
    format_schema_for_prompt,
)
from pwa.agent.pipeline.answer_agent import _extract_viz_json


# ─── VizSpec ─────────────────────────────────────────────────────────────────

class TestVizSpec:
    def test_to_dict_round_trip(self):
        spec = VizSpec(type="bar", x_col="title", y_col="revenue", reason="5 movies ranked.")
        d = spec.to_dict()
        assert d == {"type": "bar", "x_col": "title", "y_col": "revenue", "reason": "5 movies ranked."}
        restored = VizSpec.from_dict(d)
        assert restored.type == "bar"
        assert restored.x_col == "title"
        assert restored.y_col == "revenue"

    def test_from_dict_invalid_type_falls_back_to_table(self):
        spec = VizSpec.from_dict({"type": "pie", "x_col": None, "y_col": None, "reason": ""})
        assert spec.type == "table"

    def test_from_dict_empty_string_x_col_normalised_to_none(self):
        spec = VizSpec.from_dict({"type": "bar", "x_col": "", "y_col": "revenue", "reason": ""})
        assert spec.x_col is None

    def test_all_valid_types_accepted(self):
        for t in VALID_TYPES:
            spec = VizSpec.from_dict({"type": t})
            assert spec.type == t

    def test_button_label_contains_icon_and_name(self):
        spec = VizSpec(type="bar")
        label = spec.button_label()
        assert "📊" in label
        assert "Bar" in label


# ─── VizRecommendation ────────────────────────────────────────────────────────

class TestVizRecommendation:
    def test_to_dict_from_dict_round_trip(self):
        rec = VizRecommendation(
            primary=VizSpec(type="bar", x_col="genre", y_col="avg_roi", reason="8 genres ranked."),
            alternatives=[VizSpec(type="table", reason="See exact values.")],
        )
        d = rec.to_dict()
        restored = VizRecommendation.from_dict(d)
        assert restored.primary.type == "bar"
        assert len(restored.alternatives) == 1
        assert restored.alternatives[0].type == "table"

    def test_from_dict_no_alternatives_key(self):
        d = {"primary": {"type": "metric", "x_col": None, "y_col": "avg_roi", "reason": "."}}
        rec = VizRecommendation.from_dict(d)
        assert rec.primary.type == "metric"
        assert rec.alternatives == []

    def test_from_dict_missing_primary_raises(self):
        with pytest.raises((ValueError, KeyError, Exception)):
            VizRecommendation.from_dict({"alternatives": []})


# ─── build_from_shape: primary type ──────────────────────────────────────────

class TestBuildFromShape:
    def test_single_row_two_cols_gives_metric(self):
        df = pd.DataFrame([{"director_name": "Nolan", "avg_roi": 4.23}])
        rec = build_from_shape(df, "which director has highest ROI?")
        assert rec.primary.type == "metric"
        assert rec.primary.y_col == "avg_roi"

    def test_top5_movies_gives_bar(self):
        rows = [{"title": f"Movie {i}", "revenue": (5 - i) * 1_000_000} for i in range(5)]
        df = pd.DataFrame(rows)
        rec = build_from_shape(df, "top 5 highest-grossing movies")
        assert rec.primary.type == "bar"
        assert rec.primary.x_col == "title"
        assert rec.primary.y_col == "revenue"

    def test_genre_rollup_multi_numeric_gives_bar(self):
        """avg_roi_by_genre: 1 categorical + 4 numeric cols → bar."""
        genres = ["Action", "Drama", "Comedy", "Horror", "Romance", "Thriller", "Animation", "Sci-Fi"]
        df = pd.DataFrame({
            "primary_genre": genres,
            "avg_roi": [3.1, 2.4, 2.8, 4.0, 1.9, 3.5, 5.2, 2.1],
            "avg_revenue_usd": [2e8, 1.5e8, 1.2e8, 0.8e8, 0.9e8, 1.8e8, 3e8, 1.4e8],
            "avg_budget_usd": [6e7, 5e7, 4e7, 2e7, 3e7, 5e7, 4e7, 4.5e7],
            "movie_count": [450, 600, 550, 300, 350, 400, 200, 180],
        })
        rec = build_from_shape(df, "average ROI by genre")
        assert rec.primary.type == "bar"
        assert rec.primary.x_col == "primary_genre"
        assert rec.primary.y_col == "avg_roi"

    def test_year_column_gives_line(self):
        df = pd.DataFrame({"year": [2019, 2020, 2021, 2022], "revenue": [1e9, 1.2e9, 0.9e9, 1.5e9]})
        rec = build_from_shape(df, "revenue by year")
        assert rec.primary.type == "line"
        assert rec.primary.x_col == "year"

    def test_over_20_rows_gives_table(self):
        df = pd.DataFrame({"title": [f"m{i}" for i in range(21)], "revenue": range(21)})
        rec = build_from_shape(df, "all movies")
        assert rec.primary.type == "table"

    @pytest.mark.parametrize(
        "df_dict, question",
        [
            ({"avg_cast_size": 42.7}, "average cast size"),
            ({"director_name": "Christopher Nolan", "avg_roi": 4.23}, "highest average ROI director"),
            ({"director_name": "Steven Spielberg", "avg_roi": 5.4, "movie_count": 27}, "highest average ROI director"),
            ({"revenue_threshold": 500_000_000, "avg_cast_size": 42.7, "movie_count": 15}, "average cast size for movies over $500M"),
            ({"avg_budget": 1e8, "avg_revenue": 3e8, "avg_roi": 3.0, "total_movies": 50}, "overall summary"),
        ],
    )
    def test_single_row_always_returns_metric(self, df_dict, question):
        """Regression test: any DataFrame with row_count == 1 MUST return primary.type == 'metric', never 'bar', 'line', or 'table'."""
        df = pd.DataFrame([df_dict])
        rec = build_from_shape(df, question)
        assert rec.primary.type == "metric", f"Expected 'metric' for single-row DataFrame, got '{rec.primary.type}'"


# ─── build_from_shape: alternatives ──────────────────────────────────────────

class TestBuildFromShapeAlternatives:
    def test_metric_has_table_alternative(self):
        df = pd.DataFrame([{"avg_cast_size": 42.7}])
        rec = build_from_shape(df, "average cast size")
        assert any(a.type == "table" for a in rec.alternatives)

    def test_bar_has_table_alternative(self):
        rows = [{"title": f"Movie {i}", "revenue": (5 - i) * 1_000_000} for i in range(5)]
        df = pd.DataFrame(rows)
        rec = build_from_shape(df, "top 5 movies")
        assert any(a.type == "table" for a in rec.alternatives)

    def test_bar_with_trend_keyword_upgrades_primary_to_line(self):
        """When 'trend over time' is in the question, viz_router upgrades primary to line.
        The PRIMARY should be line, and bar should be offered as an alternative."""
        rows = [{"title": f"Movie {i}", "revenue": (5 - i) * 1_000_000} for i in range(5)]
        df = pd.DataFrame(rows)
        rec = build_from_shape(df, "revenue trend over time")
        # viz_router sees "trend" and the categorical col "title" → upgrades to line
        assert rec.primary.type == "line"
        # Alternatives should include bar
        alt_types = {a.type for a in rec.alternatives}
        assert "bar" in alt_types

    def test_bar_without_trend_keyword_no_line_alternative(self):
        """A plain bar-chart question (no trend keywords) should NOT offer a line alternative."""
        rows = [{"title": f"Movie {i}", "revenue": (5 - i) * 1_000_000} for i in range(5)]
        df = pd.DataFrame(rows)
        rec = build_from_shape(df, "top 5 highest-grossing movies")
        assert rec.primary.type == "bar"
        alt_types = {a.type for a in rec.alternatives}
        assert "line" not in alt_types

    def test_line_has_bar_and_table_alternatives(self):
        df = pd.DataFrame({"year": [2019, 2020, 2021, 2022], "revenue": [1e9, 1.2e9, 0.9e9, 1.5e9]})
        rec = build_from_shape(df, "revenue over time")
        alt_types = {a.type for a in rec.alternatives}
        assert "bar" in alt_types
        assert "table" in alt_types

    def test_alternatives_capped_at_two(self):
        df = pd.DataFrame({"year": [2019, 2020, 2021], "revenue": [1e9, 1.2e9, 0.9e9]})
        rec = build_from_shape(df, "revenue over time")
        assert len(rec.alternatives) <= 2

    def test_reasons_are_non_empty(self):
        rows = [{"title": f"Movie {i}", "revenue": i * 1e6} for i in range(5)]
        df = pd.DataFrame(rows)
        rec = build_from_shape(df, "top 5 movies")
        assert rec.primary.reason
        for alt in rec.alternatives:
            assert alt.reason


# ─── build_from_llm_dict ─────────────────────────────────────────────────────

class TestBuildFromLlmDict:
    def test_valid_dict_returns_recommendation(self):
        d = {
            "primary": {"type": "bar", "x_col": "title", "y_col": "revenue", "reason": "5 movies."},
            "alternatives": [{"type": "table", "x_col": None, "y_col": None, "reason": "See all."}],
        }
        rec = build_from_llm_dict(d)
        assert rec is not None
        assert rec.primary.type == "bar"
        assert rec.alternatives[0].type == "table"

    def test_invalid_primary_type_returns_none(self):
        d = {
            "primary": {"type": "pie", "x_col": "x", "y_col": "y", "reason": "Bad."},
            "alternatives": [],
        }
        rec = build_from_llm_dict(d)
        assert rec is None

    def test_none_input_returns_none(self):
        assert build_from_llm_dict(None) is None

    def test_string_input_returns_none(self):
        assert build_from_llm_dict("bar") is None  # type: ignore

    def test_missing_primary_returns_none(self):
        assert build_from_llm_dict({"alternatives": []}) is None

    def test_empty_alternatives_ok(self):
        d = {"primary": {"type": "metric", "x_col": None, "y_col": "avg_roi", "reason": "Single."}}
        rec = build_from_llm_dict(d)
        assert rec is not None
        assert rec.alternatives == []


# ─── VIZ_JSON delimiter parsing ──────────────────────────────────────────────

class TestExtractVizJson:
    def test_present_block_extracted_and_stripped(self):
        raw = (
            "The top 5 movies are Avatar, Avengers, Titanic, Star Wars, Jurassic Park.\n\n"
            "<!-- VIZ_JSON\n"
            '{"primary": {"type": "bar", "x_col": "title", "y_col": "revenue", "reason": "5 movies."}, "alternatives": []}\n'
            "-->"
        )
        answer, viz = _extract_viz_json(raw)
        assert "<!-- VIZ_JSON" not in answer
        assert "top 5 movies" in answer
        assert viz is not None
        assert viz["primary"]["type"] == "bar"

    def test_absent_block_returns_raw_and_none(self):
        raw = "The answer is 42."
        answer, viz = _extract_viz_json(raw)
        assert answer == "The answer is 42."
        assert viz is None

    def test_malformed_json_returns_clean_text_and_none(self):
        raw = "Some answer.\n<!-- VIZ_JSON\n{invalid json\n-->"
        answer, viz = _extract_viz_json(raw)
        assert "Some answer." in answer
        assert viz is None

    def test_case_insensitive_marker(self):
        raw = "Answer.\n<!-- viz_json\n{\"primary\":{\"type\":\"table\",\"x_col\":null,\"y_col\":null,\"reason\":\".\"},\"alternatives\":[]}\n-->"
        answer, viz = _extract_viz_json(raw)
        assert viz is not None
        assert viz["primary"]["type"] == "table"


# ─── format_schema_for_prompt ────────────────────────────────────────────────

class TestFormatSchemaForPrompt:
    def test_non_empty_rows_lists_cols_and_count(self):
        rows = [{"title": "Avatar", "revenue": 2.9e9}, {"title": "Titanic", "revenue": 2.2e9}]
        result = format_schema_for_prompt(rows)
        assert "title" in result
        assert "revenue" in result
        assert "2" in result  # row count

    def test_empty_rows_returns_empty_string(self):
        result = format_schema_for_prompt([])
        assert "0" in result or "empty" in result.lower()
