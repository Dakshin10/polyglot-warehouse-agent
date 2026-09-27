"""Hero component rendering client-facing empty state with interactive prompt chips."""

import streamlit as st


def render_hero_section() -> str | None:
    """Render empty state hero card with interactive prompt chips.

    Returns:
        Selected prompt string if a chip was clicked, else None.
    """
    st.markdown(
        """
        <div style="background: linear-gradient(180deg, #F8F9FA 0%, #FFFFFF 100%); border: 1px solid #E9ECEF; border-radius: 12px; padding: 1.75rem 1.5rem; margin-bottom: 2rem; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02); text-align: center;">
            <div style="display: inline-block; background: #111827; color: #FFFFFF; font-size: 0.72rem; font-weight: 600; padding: 0.2rem 0.65rem; border-radius: 20px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.75rem;">
                Governed Multi-Agent AI Analytics
            </div>
            <h2 style="font-family: 'Inter', sans-serif; font-weight: 700; font-size: 1.5rem; color: #111827; margin: 0 0 0.5rem 0; letter-spacing: -0.02em;">
                Enterprise Data Lakehouse Intelligence
            </h2>
            <p style="font-family: 'Inter', sans-serif; font-size: 0.9rem; color: #6B7280; max-width: 580px; margin: 0 auto 1.25rem auto; line-height: 1.55;">
                Ask complex analytical questions across <b>Google BigQuery</b>, <b>AlloyDB</b>, <b>Aiven MySQL</b>, and <b>Cloudflare D1</b>. Governed by 13 quality gates, AST safety guardrails, and automated viz recommendations.
            </p>
            <div style="font-size: 0.78rem; font-weight: 600; color: #374151; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.75rem;">
                Suggested Starter Queries
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2x2 Grid of Quick Prompt Chips
    chip_clicked = None
    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 Show total revenue by product category", key="hero_chip_1", use_container_width=True):
            chip_clicked = "Show total revenue by product category"
        if st.button("🏆 Show top 10 customers by overall spending", key="hero_chip_2", use_container_width=True):
            chip_clicked = "Show top 10 customers by overall spending"

    with col2:
        if st.button("📈 Show revenue growth year over year", key="hero_chip_3", use_container_width=True):
            chip_clicked = "Show revenue growth year over year"
        if st.button(
            "🏭 Show total purchase order expenditure by supplier", key="hero_chip_4", use_container_width=True
        ):
            chip_clicked = "Show total purchase order expenditure by supplier"

    return chip_clicked
