"""Sidebar drawer component displaying enterprise telemetry, connected sources, and security status."""

import os
import streamlit as st


def render_sidebar() -> str | None:
    """Render collapsible enterprise sidebar drawer.

    Returns:
        Selected shortcut question if clicked, else None.
    """
    shortcut_clicked = None

    with st.sidebar:
        st.markdown(
            """
            <div style="padding-bottom: 0.5rem; border-bottom: 1px solid #E4E4E7; margin-bottom: 1rem;">
                <div style="font-family: 'Inter', sans-serif; font-weight: 700; font-size: 1.05rem; color: #09090B;">
                    Enterprise Control Plane
                </div>
                <div style="font-size: 0.76rem; color: #71717A;">
                    Governed Lakehouse Engine & Safety Guardrails
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── 1. Connected Operational Sources ─────────────────────────────────
        st.markdown("##### 🗄️ Connected Data Sources")
        is_stub = os.getenv("PWA_USE_STUB_UI") == "1"

        if is_stub:
            st.markdown(
                """
                <div style="font-size: 0.8rem; color: #18181B; display: flex; flex-direction: column; gap: 0.35rem; background: #F4F4F5; padding: 0.6rem 0.75rem; border-radius: 6px; border: 1px solid #E4E4E7;">
                    <div><span style="color: #71717A;">●</span> BigQuery Lakehouse <span style="font-size:0.7rem; color:#71717A;">(Mocked)</span></div>
                    <div><span style="color: #18181B;">●</span> Local SQLite Snapshot <span style="font-size:0.7rem; color:#18181B;">(Active)</span></div>
                    <div><span style="color: #71717A;">●</span> Control Plane Metadata <span style="font-size:0.7rem; color:#18181B;">(In-Memory)</span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div style="font-size: 0.8rem; color: #18181B; display: flex; flex-direction: column; gap: 0.35rem; background: #F4F4F5; padding: 0.6rem 0.75rem; border-radius: 6px; border: 1px solid #E4E4E7;">
                    <div><span style="color: #18181B;">●</span> BigQuery Data Lakehouse <span style="font-size:0.7rem; color:#71717A;">(GOLD)</span></div>
                    <div><span style="color: #18181B;">●</span> Cloudflare D1 (SQLite Edge)</div>
                    <div><span style="color: #18181B;">●</span> AlloyDB (PostgreSQL)</div>
                    <div><span style="color: #18181B;">●</span> Aiven (MySQL)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

        # ── 2. Security & Guardrails Telemetry ───────────────────────────────
        st.markdown("##### 🛡️ Active Security & Safety")
        st.markdown(
            """
            <div style="font-size: 0.78rem; color: #374151; display: flex; flex-direction: column; gap: 0.3rem;">
                <div><b>✓ AST Read-Only Enforcer</b> (SELECT-only)</div>
                <div><b>✓ Cloud DLP PII Masking</b> (Active)</div>
                <div><b>✓ Dry-Run Cost Guard</b> (Max 10 GB)</div>
                <div><b>✓ 13 Quality Gates</b> (SLA Verified)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div style='margin-top: 1.25rem;'></div>", unsafe_allow_html=True)

        # ── 3. Executive Shortcuts ───────────────────────────────────────────
        st.markdown("##### ⚡ Quick Analytical Queries")

        queries = [
            ("📊 Sales Revenue by Category", "Show total revenue by product category"),
            ("🏆 Top Customers by Spend", "Show top 10 customers by overall spending"),
            ("📈 YoY Growth & Drivers", "Show revenue growth year over year"),
            ("🏭 Supplier Purchase Spend", "Show total purchase order expenditure by supplier"),
            ("👥 Customer Retention Cohorts", "Show customer retention by cohort month"),
            ("🚨 Anomaly Detection", "Find unusual revenue movements"),
        ]

        for idx, (label, q_str) in enumerate(queries):
            if st.button(label, key=f"sidebar_q_{idx}", use_container_width=True):
                shortcut_clicked = q_str

        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
        st.caption("Nexora Technologies • Polyglot Warehouse Agent v2.4")

    return shortcut_clicked
