"""Rejection panel component displaying plain, specific validation & execution errors."""

import streamlit as st


def render_rejection_panel(error_message: str, generated_sql: str | None = None) -> None:
    """Render plain, unmasked error rejection panel.

    Args:
        error_message: Detailed error message explaining what was rejected and why.
        generated_sql: Optional generated SQL that caused the rejection.
    """
    if not error_message:
        return

    sql_html = ""
    if generated_sql:
        sql_html = f"""
        <div style="margin-top: 0.75rem; margin-bottom: 0.5rem; font-family: 'Public Sans', sans-serif; font-size: 0.85rem; color: var(--slate);">
            Generated SQL:
        </div>
        <div class="pwa-mono" style="background-color: var(--paper); border: 1px solid var(--hairline); padding: 0.75rem; font-size: 0.82rem; border-radius: 4px;">
            {generated_sql}
        </div>
        """

    st.markdown(
        f"""
        <div class="pwa-error-box">
            <div class="pwa-error-title">Query Rejected</div>
            <div class="pwa-error-detail">{error_message}</div>
            {sql_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
