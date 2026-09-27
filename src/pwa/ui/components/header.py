"""Production-Grade Header component rendering top navbar with brand mark and system status."""

import os
import streamlit as st


def render_header() -> None:
    """Render top navigation bar with brand mark, status badge, and mode switcher."""
    is_stub = os.getenv("PWA_USE_STUB_UI") == "1"
    engine_status = "● Offline SQLite Engine" if is_stub else "● BigQuery Lakehouse Active"

    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown(
            """
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.35rem;">
                <div style="background: #09090B; color: #FFFFFF; font-family: 'Inter', sans-serif; font-weight: 700; font-size: 0.85rem; padding: 0.25rem 0.6rem; border-radius: 6px; letter-spacing: -0.01em;">
                    PWA
                </div>
                <div>
                    <div class="pwa-brand" style="font-size: 1.15rem; font-weight: 700; color: #09090B; line-height: 1.1;">
                        Polyglot Warehouse Agent
                    </div>
                    <div style="font-size: 0.76rem; color: #71717A; font-weight: 400; margin-top: 0.1rem;">
                        Multi-Agent Enterprise Data Analytics • <span style="color: #18181B; font-weight: 500;">v2.4 Enterprise</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div style="display: flex; flex-direction: column; align-items: flex-end; justify-content: center; gap: 0.2rem;">
                <div style="display: inline-flex; align-items: center; gap: 0.4rem; background: #F4F4F5; border: 1px solid #E4E4E7; padding: 0.2rem 0.55rem; border-radius: 20px; font-size: 0.74rem; font-weight: 500; color: #18181B;">
                    <span>{engine_status}</span>
                </div>
                <div style="font-size: 0.72rem; color: #71717A; font-weight: 400;">
                    AST Read-Only • PII Masked
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <div style="border-bottom: 1px solid #E4E4E7; margin-top: 0.6rem; margin-bottom: 1.5rem;"></div>
        """,
        unsafe_allow_html=True,
    )
