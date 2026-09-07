"""Header component rendering small top-left pwa wordmark."""

import streamlit as st


def render_header() -> None:
    """Render top header with small static pwa wordmark."""
    st.markdown(
        """
        <div style="margin-bottom: 1.25rem; border-bottom: 1px solid var(--hairline); padding-bottom: 0.75rem;">
            <div class="pwa-brand">pwa</div>
            <div class="pwa-brand-sub">Polyglot Warehouse Agent</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
