"""Answer panel component displaying synthesized answers in Public Sans typography."""

import streamlit as st


def render_answer_panel(answer: str) -> None:
    """Render synthesized NL answer in Public Sans font (unboxed, clean paragraph typography).

    Args:
        answer: Synthesized answer string from pipeline.
    """
    if not answer:
        return

    st.markdown(
        f"""
        <div class="pwa-assistant-text">
            {answer}
        </div>
        """,
        unsafe_allow_html=True,
    )
