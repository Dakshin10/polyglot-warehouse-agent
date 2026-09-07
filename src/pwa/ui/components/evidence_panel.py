"""Evidence panel component rendering collapsed expanders inside assistant turn."""

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


def render_evidence_panel(result: Any) -> None:
    """Render evidence expanders for generated SQL, results dataframe, and run metadata inside assistant turn.

    Args:
        result: PipelineResult object or dict carrying sql, rows, bytes_scanned, stage_latencies.
    """
    if isinstance(result, dict):
        sql = result.get("sql")
        rows = result.get("rows")
        bytes_scanned = result.get("bytes_scanned")
        stage_latencies = result.get("stage_latencies", {})
        row_count = result.get("count", len(rows) if rows else 0)
    else:
        sql = getattr(result, "sql", None)
        rows = getattr(result, "rows", None)
        bytes_scanned = getattr(result, "bytes_scanned", None)
        stage_latencies = getattr(result, "stage_latencies", {}) or {}
        row_count = getattr(result, "row_count", len(rows) if rows else 0)

    # 1. Generated SQL Expander
    if sql:
        with st.expander("Show generated SQL", expanded=False):
            st.code(sql, language="sql")

    # 2. Results Table Expander
    if rows is not None:
        with st.expander(f"Results table ({row_count} rows)", expanded=False):
            if rows:
                df = pd.DataFrame(rows)
                st.dataframe(df, width="stretch")
            else:
                st.markdown(
                    "<div class='pwa-quiet-meta'>No rows returned.</div>",
                    unsafe_allow_html=True,
                )

    # 3. Run Details Expander
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
