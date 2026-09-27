"""Answer panel component displaying synthesized answers in clean, human-readable executive typography."""

import re
import streamlit as st


def render_answer_panel(answer: str) -> None:
    """Render synthesized NL answer in clean, human-readable executive typography.

    Args:
        answer: Synthesized answer string from pipeline.
    """
    if not answer:
        return

    # Convert markdown bold **text** to HTML <strong>text</strong> for custom div rendering
    html_formatted = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", answer)
    # Convert line breaks to HTML breaks
    html_formatted = html_formatted.replace("\n", "<br>")

    st.markdown(
        f"""
        <div class="pwa-assistant-text" style="font-family: 'Inter', sans-serif; font-size: 0.96rem; font-weight: 400; line-height: 1.65; color: #111827; margin-bottom: 0.75rem;">
            {html_formatted}
        </div>
        """,
        unsafe_allow_html=True,
    )
