"""Stage tracker component for transient thinking status and nested pipeline trace expander."""

from typing import Dict, Optional
import streamlit as st

_STAGE_LABELS = {
    "grounding": "Grounding schema and selecting mart views…",
    "sql": "Generating SQL query…",
    "validate": "Validating AST & executing BigQuery query…",
    "synthesize": "Synthesizing natural language answer…",
}


def render_thinking_status(current_stage: str, status_msg: Optional[str] = None) -> None:
    """Render inline transient thinking indicator during live query execution.

    Args:
        current_stage: Active stage key ('grounding', 'sql', 'validate', 'synthesize').
        status_msg: Optional explicit status message override.
    """
    label = status_msg or _STAGE_LABELS.get(current_stage, f"Processing stage '{current_stage}'…")
    st.markdown(
        f"""
        <div class="pwa-thinking">
            <span class="pwa-thinking-dot"></span>
            <span>{label}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pipeline_trace_expander(
    stage_latencies: Dict[str, float] | None = None,
    stage_statuses: Dict[str, str] | None = None,
) -> None:
    """Render collapsed 'Show pipeline trace' expander inside completed assistant turn.

    Args:
        stage_latencies: Dict mapping stage_key -> duration in seconds.
        stage_statuses: Dict mapping stage_key -> status string.
    """
    latencies = stage_latencies or {}
    total_time = sum(latencies.values()) if latencies else 0.0
    statuses = stage_statuses or {}

    with st.expander(f"Show pipeline trace ({total_time:.2f}s total)", expanded=False):
        st.markdown("<div style='padding: 0.2rem 0;'>", unsafe_allow_html=True)
        st.markdown(
            "<div class='pwa-quiet-meta' style='margin-bottom: 0.5rem;'>Pipeline stage execution:</div>",
            unsafe_allow_html=True,
        )

        stages = [
            ("grounding", "1. Schema Grounding"),
            ("sql", "2. SQL Generation"),
            ("exec", "3. Validation & Execution"),
            ("answer", "4. Answer Synthesis"),
        ]

        for key, name in stages:
            lat = latencies.get(key)
            status_val = statuses.get(key, "")

            if status_val == "cached" or (lat is None or lat == 0.0):
                badge_html = '<span class="pwa-pill pwa-pill-cached">cached</span>'
                lat_text = ""
            elif status_val == "template":
                badge_html = '<span class="pwa-pill pwa-pill-template">template-match</span>'
                lat_text = (
                    f" <span class='pwa-mono' style='font-size:0.8rem; color:var(--pwa-text-secondary);'>({lat:.2f}s)</span>"
                    if lat
                    else ""
                )
            else:
                badge_html = '<span class="pwa-pill pwa-pill-llm">LLM-fallback</span>'
                lat_text = (
                    f" <span class='pwa-mono' style='font-size:0.8rem; color:var(--pwa-text-secondary);'>({lat:.2f}s)</span>"
                    if lat
                    else ""
                )

            st.markdown(
                f"""
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.35rem;">
                    <span class="pwa-mono" style="font-size: 0.82rem; color: var(--pwa-text-primary);">{name}</span>
                    <div>
                        {badge_html}
                        {lat_text}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)
