"""Visualization router — shape-based heuristics only, no LLM calls.

Given a pandas DataFrame and the original question string, decides which
Streamlit component best represents the result:

  - "metric"  →  st.metric  (1 row, ≤2 cols)
  - "bar"     →  st.bar_chart  (2-20 rows, 1 categorical + 1-N numeric cols,
                                 plots the first numeric as y)
  - "line"    →  st.line_chart (datetime/year col + 1 numeric col, or trend keywords)
  - "table"   →  st.dataframe (everything else: >20 rows, 0 categorical cols, etc.)

Returns a dict::

    {
        "type": "bar" | "line" | "table" | "metric",
        "x": str | None,   # column name to use as index / x-axis
        "y": str | None,   # column name to use as value / y-axis
    }
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

# Keywords that strongly suggest the user wants a time-series / trend chart
_TREND_KEYWORDS: tuple[str, ...] = (
    "trend",
    "over time",
    "by year",
    "per year",
    "by month",
    "per month",
    "over the years",
    "annually",
    "year over year",
    "yoy",
    "time series",
    "historical",
)

# Patterns that identify year-like columns by name
_YEAR_COL_PATTERN = re.compile(r"\b(year|yr|date|month|quarter|period)\b", re.IGNORECASE)


def _is_numeric(series) -> bool:  # type: ignore[type-arg]
    """Return True if the pandas Series holds numeric data."""
    import pandas as pd  # local import to keep module importable without pandas at import time

    return pd.api.types.is_numeric_dtype(series)


def _is_datetime_or_year(series, col_name: str) -> bool:  # type: ignore[type-arg]
    """Return True if the column looks like a time/year axis."""
    import pandas as pd

    # Explicit datetime dtype
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    # Integer column whose name contains year/date/month/etc
    if pd.api.types.is_integer_dtype(series) and _YEAR_COL_PATTERN.search(col_name):
        return True
    # String column that looks like "YYYY"
    if pd.api.types.is_object_dtype(series):
        sample = series.dropna().head(5).astype(str)
        if all(re.fullmatch(r"\d{4}", v) for v in sample):
            return True
    return False


def _has_trend_keyword(question: str) -> bool:
    """Return True if the question contains any trend/time-series keyword."""
    q_lower = question.lower()
    return any(kw in q_lower for kw in _TREND_KEYWORDS)


def choose_visualization(df: "pd.DataFrame", question: str) -> dict:
    """Choose the best visualization type based purely on DataFrame shape.

    Args:
        df: The result DataFrame (may be empty).
        question: The original natural-language question asked by the user.

    Returns:
        A dict with keys ``"type"``, ``"x"``, ``"y"`` where type is one of
        ``"metric" | "bar" | "line" | "table"``.
    """
    _fallback = {"type": "table", "x": None, "y": None}

    if df is None or df.empty:
        return _fallback

    row_count = len(df)
    cols = list(df.columns)

    # ── Rule 1: single-row aggregate → metric ──────────────────────────────
    if row_count == 1:
        numeric_cols = [c for c in cols if _is_numeric(df[c])]
        meaningful_numerics = [
            c for c in numeric_cols if not re.search(r"(_|^)(id|rank|year|yr|date|threshold)(_|s|$)", c, re.IGNORECASE)
        ]
        candidates = meaningful_numerics if meaningful_numerics else numeric_cols

        metric_named = [
            c
            for c in candidates
            if re.search(
                r"(avg|sum|total|mean|roi|rate|ratio|count|size|revenue|budget|profit|score|pct|percent)",
                c,
                re.IGNORECASE,
            )
        ]
        y_col = metric_named[0] if metric_named else (candidates[0] if candidates else cols[-1])
        return {"type": "metric", "x": None, "y": y_col}

    # ── Rule 2: too many rows → table ─────────────────────────────────────
    if row_count > 20:
        return _fallback

    # ── Below this point: 2–20 rows ───────────────────────────────────────

    numeric_cols = [c for c in cols if _is_numeric(df[c])]
    categorical_cols = [c for c in cols if c not in numeric_cols]

    # Separate out datetime/year-like columns from "generic" categoricals
    datetime_cols = [c for c in categorical_cols if _is_datetime_or_year(df[c], c)]
    # Also check integer columns for year-like names
    datetime_cols += [c for c in numeric_cols if _is_datetime_or_year(df[c], c)]
    datetime_cols = list(dict.fromkeys(datetime_cols))  # deduplicate, preserve order

    # Numeric cols that are NOT datetime axis or row index / rank
    non_metric_patterns = re.compile(r"^(rank|id|_id|row_num|row_number)$", re.IGNORECASE)
    value_numeric_cols = [c for c in numeric_cols if c not in datetime_cols and not non_metric_patterns.search(c)]
    if not value_numeric_cols:
        value_numeric_cols = [c for c in numeric_cols if c not in datetime_cols]

    trend_signal = _has_trend_keyword(question)

    # ── Rule 3: datetime/year col + exactly one value numeric col → line ──
    if datetime_cols and len(value_numeric_cols) == 1:
        return {"type": "line", "x": datetime_cols[0], "y": value_numeric_cols[0]}

    # ── Rule 4: trend keyword upgrades ambiguous bar → line ───────────────
    # (one categorical + one numeric, but question says "over time" / "by year")
    pure_categoricals = [c for c in categorical_cols if c not in datetime_cols]
    if trend_signal and pure_categoricals and len(value_numeric_cols) == 1:
        return {"type": "line", "x": pure_categoricals[0], "y": value_numeric_cols[0]}

    # ── Rule 5: categorical + numeric → bar ────────────────────────────────
    # Use first categorical column (preferring title/name/director/genre) as x,
    # and first value numeric column as y.
    if pure_categoricals and value_numeric_cols:
        title_cats = [
            c for c in pure_categoricals if re.search(r"(title|name|director|genre|studio|actor)", c, re.IGNORECASE)
        ]
        x_col = title_cats[0] if title_cats else pure_categoricals[0]
        return {"type": "bar", "x": x_col, "y": value_numeric_cols[0]}

    # ── Rule 6: one numeric col, no usable categorical → bar (use index) ──
    if not pure_categoricals and len(value_numeric_cols) == 1 and not datetime_cols:
        return {"type": "bar", "x": None, "y": value_numeric_cols[0]}

    # ── Default: too complex → table ──────────────────────────────────────
    return _fallback
