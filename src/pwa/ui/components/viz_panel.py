"""Streamlit component for rendering the primary visualization + alternative switcher.

Layout inside a single assistant turn:
  ┌─────────────────────────────────────────────────────────┐
  │  st.caption(reason)                                      │
  │  <primary chart / metric / scatter / table>              │
  │  [📊 Bar chart ✓]  [🗄️ Table view]  [📈 Line chart]    │  ← alt buttons
  └─────────────────────────────────────────────────────────┘
  (existing "Results table" expander below, unchanged)

Session state key: ``viz_sel_{msg_idx}`` — integer index into the flat list
``[primary_spec, *alternatives]``.  Defaults to 0 (primary).
Clicking a non-active button sets the index and calls ``st.rerun()``.
No new query, no new LLM call — purely a client-side re-render.
"""

from __future__ import annotations


import pandas as pd
import streamlit as st


# ─── Chart dispatch ───────────────────────────────────────────────────────────


def _render_chart_for_spec(
    df: pd.DataFrame,
    spec_type: str,
    x_col: str | None,
    y_col: str | None,
) -> None:
    """Render the appropriate Streamlit chart component for *spec_type*."""
    try:
        if spec_type == "metric":
            val_col = y_col if y_col and y_col in df.columns else df.columns[-1]
            value = df[val_col].iloc[0]
            if isinstance(value, float):
                formatted = f"{value:,.2f}"
            elif isinstance(value, int):
                formatted = f"{value:,}"
            else:
                formatted = str(value)
            st.metric(label=str(val_col).replace("_", " ").title(), value=formatted)

        elif spec_type == "bar":
            if x_col and x_col in df.columns and y_col and y_col in df.columns:
                st.bar_chart(df.set_index(x_col)[y_col])
            elif y_col and y_col in df.columns:
                st.bar_chart(df[y_col])
            else:
                st.bar_chart(df.iloc[:, -1])

        elif spec_type == "line":
            if x_col and x_col in df.columns and y_col and y_col in df.columns:
                st.line_chart(df.set_index(x_col)[y_col])
            elif y_col and y_col in df.columns:
                st.line_chart(df[y_col])
            else:
                st.line_chart(df.iloc[:, -1])

        elif spec_type == "scatter":
            if x_col and x_col in df.columns and y_col and y_col in df.columns:
                st.scatter_chart(df, x=x_col, y=y_col)
            elif y_col and y_col in df.columns:
                st.scatter_chart(df, y=y_col)
            else:
                st.scatter_chart(df)

        elif spec_type == "table":
            try:
                st.dataframe(df, use_container_width=True)
            except Exception:
                st.table(df)

    except Exception as exc:
        # Chart rendering is best-effort; never crash the UI
        st.caption(f"⚠️ Could not render {spec_type} chart: {exc}")


# ─── Button helpers ───────────────────────────────────────────────────────────

_TYPE_ICONS = {
    "bar": "📊",
    "line": "📈",
    "scatter": "🔵",
    "table": "🗄️",
    "metric": "🔢",
}
_TYPE_LABELS = {
    "bar": "Bar chart",
    "line": "Line chart",
    "scatter": "Scatter plot",
    "table": "Table view",
    "metric": "Metric",
}


def _btn_label(spec_type: str) -> str:
    icon = _TYPE_ICONS.get(spec_type, "📉")
    label = _TYPE_LABELS.get(spec_type, spec_type.title())
    return f"{icon} {label}"


# ─── Public render function ───────────────────────────────────────────────────


def render_viz_panel(
    df: pd.DataFrame,
    recommendation_dict: dict | None,
    msg_idx: int,
    question: str = "",
    auto_confirm: bool = False,
) -> None:
    """Render HITL visualization recommendation banner + primary chart once confirmed.

    Args:
        df:                  The result DataFrame (already fetched, no new query).
        recommendation_dict: ``VizRecommendation.to_dict()`` output or ``None``.
                             Falls back to shape heuristics if ``None``.
        msg_idx:             Stable message index from the ``enumerate`` loop in
                             ``app.py``; used as the ``session_state`` key.
        question:            Original question (used only for shape-fallback).
        auto_confirm:        If True, bypasses HITL prompt and renders graph directly.
    """
    if df is None or df.empty:
        return

    # ── Resolve recommendation ────────────────────────────────────────────────
    if not recommendation_dict:
        try:
            from pwa.ui.viz_recommendation import build_from_shape

            recommendation_dict = build_from_shape(df, question).to_dict()
        except Exception as exc:
            import logging

            logging.getLogger("pwa.ui.viz_panel").error(f"Viz recommendation shape build error: {exc}", exc_info=True)
            st.caption(f"⚠️ Could not compute visual recommendation: {exc}")
            return

    primary_d = recommendation_dict.get("primary", {})
    alternatives_d = recommendation_dict.get("alternatives", [])

    # Build flat list: index 0 = primary, 1..n = alternatives
    all_specs: list[dict] = [primary_d] + list(alternatives_d)

    primary_type = primary_d.get("type", "table")

    # Only offer graph generation HITL prompt for actual chart/graph types (bar, line, scatter)
    is_graph_type = primary_type in ("bar", "line", "scatter")
    if not is_graph_type and not auto_confirm:
        return

    # ── HITL Confirmation State ───────────────────────────────────────────────
    confirm_key = f"viz_confirmed_{msg_idx}"
    if auto_confirm:
        st.session_state[confirm_key] = True
    elif confirm_key not in st.session_state:
        st.session_state[confirm_key] = False

    # Check if user has confirmed graph generation
    if not st.session_state[confirm_key]:
        primary_label = _TYPE_LABELS.get(primary_type, primary_type.title())
        primary_icon = _TYPE_ICONS.get(primary_type, "📊")
        reason = primary_d.get("reason", "")

        # HITL recommendation banner for graphs
        st.markdown(
            f"""
            <div style="background: rgba(13, 110, 253, 0.04); border: 1px dashed rgba(13, 110, 253, 0.3); border-radius: 10px; padding: 0.85rem 1.15rem; margin-bottom: 0.75rem;">
                <div style="font-weight: 600; font-size: 0.92rem; color: var(--pwa-text-primary); margin-bottom: 0.25rem;">
                    💡 Graph Visualization Recommended: <span style="color: #0d6efd;">{primary_icon} {primary_label}</span>
                </div>
                <div style="font-size: 0.85rem; color: var(--pwa-text-secondary);">
                    {reason or f"The AI detected that this data is best visualized using a {primary_label}."}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_conf, _ = st.columns([1, 1])
        with col_conf:
            if st.button(
                f"{primary_icon} Generate {primary_label}",
                key=f"btn_confirm_viz_{msg_idx}",
                help="Click to generate and view this graph visualization (Human-in-the-loop confirmation)",
            ):
                st.session_state[confirm_key] = True
                st.rerun()
        return

    # ── Session state for chart selection ─────────────────────────────────────
    state_key = f"viz_sel_{msg_idx}"
    if state_key not in st.session_state:
        st.session_state[state_key] = 0  # default to primary

    active_idx: int = st.session_state[state_key]
    # Guard against stale index
    if active_idx >= len(all_specs):
        active_idx = 0
        st.session_state[state_key] = 0

    active_spec = all_specs[active_idx]
    spec_type = active_spec.get("type", "table")
    x_col = active_spec.get("x_col") or None
    y_col = active_spec.get("y_col") or None
    reason = active_spec.get("reason", "")

    # ── Caption + chart ───────────────────────────────────────────────────────
    if reason:
        st.caption(reason)

    _render_chart_for_spec(df, spec_type, x_col, y_col)

    # ── Alternative switcher buttons + Hide button ───────────────────────────
    num_btns = len(all_specs) + 1
    cols = st.columns(num_btns)
    for i, (col, spec) in enumerate(zip(cols[: len(all_specs)], all_specs)):
        stype = spec.get("type", "table")
        label = _btn_label(stype)
        is_active = i == active_idx
        btn_key = f"viz_btn_{msg_idx}_{i}"
        with col:
            if is_active:
                st.button(f"✓ {label}", key=btn_key, disabled=True)
            else:
                if st.button(label, key=btn_key):
                    st.session_state[state_key] = i
                    st.rerun()

    with cols[-1]:
        if st.button("🙈 Hide graph", key=f"btn_hide_viz_{msg_idx}", help="Hide visualization"):
            st.session_state[confirm_key] = False
            st.rerun()
