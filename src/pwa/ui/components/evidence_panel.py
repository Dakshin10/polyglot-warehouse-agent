"""Evidence panel component rendering collapsed expanders inside assistant turn.

Renders in order:
  1. Structured viz panel (primary chart + reason caption + alternative buttons)
  2. Generated SQL expander (collapsed)
  3. Results table expander (always present — chart supplements, never replaces)
  4. Run details expander (collapsed)
"""

from typing import Any, Optional
import pandas as pd
import streamlit as st


def _format_bytes(bytes_count: Optional[int]) -> str:
    """Format bytes into human-readable B, KB, MB, GB string."""
    if bytes_count is None:
        return "0 B (Cached / Schema only)"
    if bytes_count < 1024:
        return f"{bytes_count} B"
    elif bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f} KB"
    elif bytes_count < 1024 * 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"


def render_evidence_panel(
    result: Any,
    question: str = "",
    msg_idx: int = 0,
) -> None:
    """Render evidence expanders for generated SQL, results dataframe, and run metadata.

    Args:
        result:   PipelineResult object or dict carrying sql, rows, bytes_scanned,
                  stage_latencies, viz_recommendation.
        question: Original natural-language question.  Passed to the viz panel so
                  the shape-based fallback can apply keyword heuristics.
        msg_idx:  Stable message index from app.py's enumerate loop.  Used as the
                  session_state key for alternative chart button state.
    """
    if isinstance(result, dict):
        sql = result.get("sql")
        rows = result.get("rows")
        bytes_scanned = result.get("bytes_scanned")
        stage_latencies = result.get("stage_latencies", {})
        row_count = result.get("count", len(rows) if rows else 0)
        viz_rec_dict = result.get("viz_recommendation")
    else:
        sql = getattr(result, "sql", None)
        rows = getattr(result, "rows", None)
        bytes_scanned = getattr(result, "bytes_scanned", None)
        stage_latencies = getattr(result, "stage_latencies", {}) or {}
        row_count = getattr(result, "row_count", len(rows) if rows else 0)
        viz_rec_dict = getattr(result, "viz_recommendation", None)

    # ── 0. Structured viz panel (chart + reason + alternative buttons) ─────────
    if rows:
        df = pd.DataFrame(rows)
        try:
            from pwa.ui.components.viz_panel import render_viz_panel

            render_viz_panel(df, viz_rec_dict, msg_idx=msg_idx, question=question)
        except Exception:
            # Visualization is best-effort; never crash the UI over a chart
            pass

    # ── 1. Generated SQL Expander ─────────────────────────────────────────────
    if sql:
        with st.expander("Show generated SQL", expanded=False):
            st.code(sql, language="sql")

    # ── 2. Results Table Expander (always present when there are rows) ─────────
    if rows is not None:
        with st.expander(f"Results table ({row_count} rows)", expanded=False):
            if rows:
                df = pd.DataFrame(rows)
                try:
                    st.dataframe(df, width="stretch")
                except Exception:
                    st.table(df)
            else:
                st.markdown(
                    "<div class='pwa-quiet-meta'>No rows returned.</div>",
                    unsafe_allow_html=True,
                )

    # ── 3. Run Details Expander ───────────────────────────────────────────────
    total_latency = sum(stage_latencies.values()) if stage_latencies else 0.0
    bytes_str = _format_bytes(bytes_scanned)
    summary_meta = f"Run details — {bytes_str} scanned · {total_latency:.2f}s total"

    with st.expander(summary_meta, expanded=False):
        st.markdown(
            f"""
            <div class="pwa-quiet-meta" style="display: flex; flex-direction: column; gap: 0.25rem;">
                <div>Bytes scanned: <span class="pwa-mono" style="color: var(--pwa-text-primary);">{bytes_str}</span></div>
                <div>Row count: <span class="pwa-mono" style="color: var(--pwa-text-primary);">{row_count}</span></div>
                <div>Total latency: <span class="pwa-mono" style="color: var(--pwa-text-primary);">{total_latency:.2f}s</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── 4. Generate Report Deliverable Button ─────────────────────────────────
    report_btn_key = f"gen_report_btn_{msg_idx}"
    if st.button("📄 Generate report", key=report_btn_key, help="View as shareable analytical deliverable report"):
        st.session_state.active_report = {
            "question": question,
            "result": result,
        }
        st.session_state.active_view = "report"
        st.rerun()
