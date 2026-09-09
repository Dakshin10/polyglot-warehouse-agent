"""Visualization recommendation schema and fast-path builder.

Defines VizSpec / VizRecommendation dataclasses (with dict round-trip) and
``build_from_shape()`` — a pure shape-heuristic builder that wraps the existing
viz_router with templated reasons and 1-2 deterministic alternatives.

Used by:
  * orchestrator.py (fast template-match path) — zero LLM calls
  * answer_agent.py (LLM-fallback path) — validates LLM JSON with ``from_dict``
  * viz_panel.py (Streamlit rendering) — reads the dict from session_state
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

# ─── Valid types ──────────────────────────────────────────────────────────────
VALID_TYPES = frozenset({"bar", "line", "scatter", "table", "metric"})

_TYPE_ICONS = {
    "bar": "📊",
    "line": "📈",
    "scatter": "🔵",
    "table": "🗄️",
    "metric": "🔢",
}


# ─── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class VizSpec:
    """A single chart recommendation."""

    type: str            # one of VALID_TYPES
    x_col: str | None = None
    y_col: str | None = None
    reason: str = ""

    def icon(self) -> str:
        return _TYPE_ICONS.get(self.type, "📉")

    def button_label(self) -> str:
        labels = {
            "bar": "Bar chart",
            "line": "Line chart",
            "scatter": "Scatter plot",
            "table": "Table view",
            "metric": "Metric",
        }
        return f"{self.icon()} {labels.get(self.type, self.type.title())}"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "x_col": self.x_col,
            "y_col": self.y_col,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VizSpec":
        t = str(d.get("type", "table")).lower()
        if t not in VALID_TYPES:
            t = "table"
        return cls(
            type=t,
            x_col=d.get("x_col") or None,
            y_col=d.get("y_col") or None,
            reason=str(d.get("reason", "")),
        )


@dataclass
class VizRecommendation:
    """Primary chart plus 0-2 alternative chart types for the same data."""

    primary: VizSpec
    alternatives: list[VizSpec] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "primary": self.primary.to_dict(),
            "alternatives": [a.to_dict() for a in self.alternatives],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VizRecommendation":
        if not isinstance(d, dict) or "primary" not in d:
            raise ValueError("VizRecommendation dict must have a 'primary' key")
        primary = VizSpec.from_dict(d["primary"])
        alternatives = [VizSpec.from_dict(a) for a in d.get("alternatives", []) if isinstance(a, dict)]
        return cls(primary=primary, alternatives=alternatives)


# ─── Templated reason strings ─────────────────────────────────────────────────

def _bar_reason(x_col: str | None, y_col: str | None, n: int) -> str:
    x = x_col or "category"
    y = y_col or "value"
    return (
        f"{n} {'entry' if n == 1 else 'entries'} of '{x}' ranked by '{y}' — "
        "a bar chart makes the ordering immediately scannable."
    )


def _line_reason(x_col: str | None, y_col: str | None, n: int) -> str:
    x = x_col or "time axis"
    y = y_col or "value"
    return (
        f"'{y}' plotted over '{x}' — a line chart reveals the trend and direction of change."
    )


def _metric_reason(y_col: str | None) -> str:
    label = y_col or "aggregate"
    return f"Single '{label}' value — surfaced as a metric for immediate at-a-glance visibility."


def _table_reason(n_rows: int, n_cols: int) -> str:
    return (
        f"{n_rows} rows × {n_cols} columns — a table preserves all detail "
        "and exact values for every column."
    )


def _scatter_reason(x_col: str | None, y_col: str | None) -> str:
    x = x_col or "X"
    y = y_col or "Y"
    return (
        f"'{x}' vs '{y}' as two numeric dimensions — "
        "a scatter plot reveals the distribution and correlation."
    )


# ─── Alternative generation ───────────────────────────────────────────────────

def _build_alternatives(primary: VizSpec, df: "pd.DataFrame", question: str) -> list[VizSpec]:
    """Generate 0-2 deterministic alternative VizSpecs for a given primary."""
    n_rows, n_cols = len(df), len(df.columns)
    ptype = primary.type
    alts: list[VizSpec] = []

    if ptype == "metric":
        # Offer a table so the user can see if there are other rows
        alts.append(VizSpec(
            type="table",
            reason=_table_reason(n_rows, n_cols),
        ))

    elif ptype == "bar":
        # Always offer table (exact numbers)
        alts.append(VizSpec(
            type="table",
            x_col=primary.x_col,
            y_col=primary.y_col,
            reason=_table_reason(n_rows, n_cols),
        ))
        # Upgrade to line only if question has trend signal
        if _has_trend_keyword(question):
            alts.append(VizSpec(
                type="line",
                x_col=primary.x_col,
                y_col=primary.y_col,
                reason=_line_reason(primary.x_col, primary.y_col, n_rows),
            ))

    elif ptype == "line":
        # Offer bar (period-by-period comparison) + table
        alts.append(VizSpec(
            type="bar",
            x_col=primary.x_col,
            y_col=primary.y_col,
            reason=_bar_reason(primary.x_col, primary.y_col, n_rows),
        ))
        alts.append(VizSpec(
            type="table",
            reason=_table_reason(n_rows, n_cols),
        ))

    elif ptype == "table":
        # Try to offer a bar if a cat+num pair exists
        from pwa.ui.viz_router import _is_numeric  # type: ignore[attr-defined]
        cols = list(df.columns)
        num_cols = [c for c in cols if _is_numeric(df[c])]
        cat_cols = [c for c in cols if c not in num_cols]
        if cat_cols and num_cols:
            x = cat_cols[0]
            y = num_cols[0]
            alts.append(VizSpec(
                type="bar",
                x_col=x,
                y_col=y,
                reason=_bar_reason(x, y, n_rows),
            ))

    elif ptype == "scatter":
        alts.append(VizSpec(
            type="table",
            reason=_table_reason(n_rows, n_cols),
        ))

    return alts[:2]  # cap at 2 alternatives


# ─── Trend keyword helper (mirrors viz_router) ────────────────────────────────

_TREND_KEYWORDS = (
    "trend", "over time", "by year", "per year", "by month", "per month",
    "over the years", "annually", "year over year", "yoy", "time series", "historical",
)


def _has_trend_keyword(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _TREND_KEYWORDS)


# ─── Public builders ──────────────────────────────────────────────────────────

def build_from_shape(df: "pd.DataFrame", question: str) -> VizRecommendation:
    """Build a VizRecommendation using shape-based heuristics only — 0 LLM calls.

    Uses the existing viz_router.choose_visualization for the primary pick and
    generates templated reasons + 1-2 deterministic alternatives.
    """
    from pwa.ui.viz_router import choose_visualization

    n_rows, n_cols = len(df), len(df.columns)
    viz = choose_visualization(df, question)
    vtype = viz["type"]
    x_col = viz["x"]
    y_col = viz["y"]

    if vtype == "metric":
        reason = _metric_reason(y_col)
    elif vtype == "bar":
        reason = _bar_reason(x_col, y_col, n_rows)
    elif vtype == "line":
        reason = _line_reason(x_col, y_col, n_rows)
    elif vtype == "scatter":
        reason = _scatter_reason(x_col, y_col)
    else:
        reason = _table_reason(n_rows, n_cols)

    primary = VizSpec(type=vtype, x_col=x_col, y_col=y_col, reason=reason)
    alternatives = _build_alternatives(primary, df, question)
    return VizRecommendation(primary=primary, alternatives=alternatives)


def build_from_llm_dict(d: object) -> VizRecommendation | None:
    """Validate and construct a VizRecommendation from an LLM-supplied dict.

    Returns None if the dict is missing, malformed, or the primary type is not
    one of the recognised VALID_TYPES.  The caller should fall back to
    ``build_from_shape`` when None is returned.

    Note: ``VizSpec.from_dict`` normalises unknown types to ``"table"`` to be
    permissive for alternatives, but here we explicitly reject unknown primary
    types so that an LLM hallucinating "pie" or "heatmap" is caught.
    """
    if not isinstance(d, dict):
        return None
    primary_raw = d.get("primary")
    if not isinstance(primary_raw, dict):
        return None
    raw_type = str(primary_raw.get("type", "")).lower()
    if raw_type not in VALID_TYPES:
        return None
    try:
        return VizRecommendation.from_dict(d)
    except Exception:
        return None


def format_schema_for_prompt(rows: list[dict]) -> str:
    """Format column names + dtypes + row count for injection into the LLM prompt."""
    if not rows:
        return "Result: empty (0 rows)."
    try:
        import pandas as pd
        df = pd.DataFrame(rows)
        col_parts = ", ".join(f"{col} ({dtype})" for col, dtype in df.dtypes.items())
        return f"Columns: {col_parts}. Row count: {len(df)}."
    except Exception:
        # Fallback: just list column names
        col_names = ", ".join(str(k) for k in rows[0].keys())
        return f"Columns: {col_names}. Row count: {len(rows)}."
