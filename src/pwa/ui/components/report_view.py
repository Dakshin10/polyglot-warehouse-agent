"""Streamlit component for rendering the PWA Analytical Deliverable Report View (Production Grade)."""

from __future__ import annotations

import datetime
from typing import Any
import pandas as pd
import streamlit as st

from pwa.ui.components.viz_panel import render_viz_panel
from pwa.ui.pdf_export import generate_report_pdf


def format_markdown_report(
    question: str,
    answer: str,
    sql: str | None,
    rows: list[dict] | None,
    routing_path: str,
    timestamp: str,
    guardrails: list[dict] | None,
    provenance: list[dict] | None,
    bytes_scanned: int | None,
    row_count: int,
) -> str:
    """Format full report deliverable as clean shareable Markdown."""
    lines = [
        f"# Analytical Deliverable Report: {question}",
        "",
        f"**Executed**: `{timestamp}`  ",
        f"**Routing Path**: `{routing_path}`  ",
        f"**Row Count**: `{row_count}`  ",
        f"**Bytes Scanned**: `{bytes_scanned or 0:,} bytes`  ",
        "",
        "---",
        "",
        "## Executive Headline Finding",
        "",
        answer,
        "",
        "---",
        "",
        "## Methodology & Executed SQL",
        "",
        "```sql",
        sql or "-- No SQL executed",
        "```",
        "",
        "---",
        "",
        "## Data Provenance",
        "",
    ]

    if provenance:
        for p in provenance:
            lines.append(
                f"- **Table**: `{p.get('table_name')}` ({p.get('type')}) | **Last Refreshed**: `{p.get('last_refreshed')}`"
            )
    else:
        lines.append("- Dynamic query over base warehouse views")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Guardrails & Security Rules Applied",
            "",
        ]
    )

    if guardrails:
        for g in guardrails:
            lines.append(f"- **[{g.get('name')}]**: {g.get('description')}")
    else:
        lines.append("- Standard AST read-only validation applied")

    lines.extend(
        [
            "",
            "---",
            "",
            f"## Full Results Data Table ({row_count} rows)",
            "",
        ]
    )

    if rows and len(rows) > 0:
        try:
            df = pd.DataFrame(rows)
            lines.append(df.to_markdown(index=False))
        except Exception:
            lines.append(str(rows))

    return "\n".join(lines)


def render_report_view(report_data: dict[str, Any]) -> None:
    """Render the full analytical deliverable report view page."""
    question = report_data.get("question", "")
    result = report_data.get("result")

    # Extract attributes safely from PipelineResult or dict
    answer_raw = getattr(result, "answer", None) or (result.get("answer") if isinstance(result, dict) else "")
    answer: str = str(answer_raw) if answer_raw is not None else ""
    sql = getattr(result, "sql", None) or (result.get("sql") if isinstance(result, dict) else "")
    rows = getattr(result, "rows", None) or (result.get("rows") if isinstance(result, dict) else [])
    bytes_scanned = getattr(result, "bytes_scanned", 0) or 0
    slot_ms = getattr(result, "slot_ms", 0) or 0
    row_count = getattr(result, "row_count", 0) or (len(rows) if rows else 0)
    viz_rec = getattr(result, "viz_recommendation", None) or (
        result.get("viz_recommendation") if isinstance(result, dict) else None
    )
    stage_details = getattr(result, "stage_details", {}) or (
        result.get("stage_details") if isinstance(result, dict) else {}
    )

    routing_path = (
        stage_details.get("routing_path", "Governed-SQL") if isinstance(stage_details, dict) else "Governed-SQL"
    )
    executed_at = (
        getattr(result, "executed_at", None)
        or report_data.get("timestamp")
        or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )

    guardrails = getattr(result, "guardrails_applied", []) or report_data.get("guardrails_applied", [])
    provenance = getattr(result, "data_provenance", []) or report_data.get("data_provenance", [])

    # Navigation Header
    col_nav, col_actions = st.columns([1, 1])
    with col_nav:
        if st.button("← Return to Interactive Chat", key="btn_back_to_chat"):
            st.session_state.active_view = "chat"
            st.rerun()

    with col_actions:
        st.markdown(
            f"""
            <div style="text-align: right; font-size: 0.78rem; color: #6B7280;">
                Document Ref: <span class="pwa-mono" style="color: #111827; font-weight: 600;">PWA-REP-{hash(question) & 0xFFFFFF:06X}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        "<div style='border-bottom: 1px solid #E5E7EB; margin: 0.75rem 0 1.25rem 0;'></div>", unsafe_allow_html=True
    )

    # 1. Executive Document Title Card
    st.markdown(
        f"""
        <div style="background: #111827; color: #FFFFFF; border-radius: 8px; padding: 1.25rem 1.5rem; margin-bottom: 1.5rem;">
            <div style="font-size: 0.75rem; text-transform: uppercase; tracking: 0.05em; color: #9CA3AF; margin-bottom: 0.25rem;">
                Executive Analytical Deliverable
            </div>
            <h2 style="font-family: 'Inter', sans-serif; font-size: 1.35rem; font-weight: 700; margin: 0 0 0.5rem 0; color: #FFFFFF;">
                {question}
            </h2>
            <div style="font-size: 0.78rem; color: #D1D5DB; display: flex; gap: 1.25rem; flex-wrap: wrap;">
                <span>⏱ Executed: <b>{executed_at}</b></span>
                <span>⚡ Path: <b>{routing_path}</b></span>
                <span>🛡 Status: <b>AST Validated</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2. Executive Headline Finding Card
    st.markdown(
        f"""
        <div style="background: #F9FAFB; border: 1px solid #E5E7EB; border-left: 4px solid #111827; border-radius: 6px; padding: 1.15rem 1.25rem; margin-bottom: 1.5rem;">
            <div style="font-weight: 700; font-size: 0.88rem; color: #111827; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.4rem;">
                💡 Executive Finding
            </div>
            <div style="font-family: 'Inter', sans-serif; font-size: 0.95rem; font-weight: 600; color: #111827; line-height: 1.6;">
                {answer}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 3. Primary Chart Visual Delivery
    if rows:
        df = pd.DataFrame(rows)
        render_viz_panel(df, viz_rec, msg_idx=999, question=question, auto_confirm=True)

    st.markdown("<div style='border-bottom: 1px solid #E5E7EB; margin: 1.5rem 0;'></div>", unsafe_allow_html=True)

    # 4. Methodology & Executed SQL
    with st.expander("🔬 Methodology & Governed SQL Execution", expanded=True):
        if sql:
            st.code(sql, language="sql")
        else:
            st.write("No SQL query recorded for this deliverable.")

    # 5. Governance & Metadata Grids
    col_prov, col_guards = st.columns(2)

    with col_prov:
        st.markdown("##### 🛡️ Data Provenance")
        if provenance:
            for p in provenance:
                t_name = p.get("table_name", "Unknown Table")
                t_type = p.get("type", "table")
                t_refresh = p.get("last_refreshed", "Live")
                st.markdown(
                    f"<div style='font-size: 0.82rem; color: #374151; margin-bottom: 0.25rem;'>• <b><code>{t_name}</code></b> ({t_type})<br><span style='color: #6B7280; font-size: 0.75rem;'>Refreshed: {t_refresh}</span></div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                "<div style='font-size: 0.82rem; color: #6B7280;'>• Dynamic execution over base BigQuery lakehouse gold views.</div>",
                unsafe_allow_html=True,
            )

    with col_guards:
        st.markdown("##### 🛑 Security & Quality Rules")
        if guardrails:
            for g in guardrails:
                st.markdown(
                    f"<div style='font-size: 0.82rem; color: #374151; margin-bottom: 0.25rem;'>• <b>{g.get('name')}</b><br><span style='color: #6B7280; font-size: 0.75rem;'>{g.get('description')}</span></div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                "<div style='font-size: 0.82rem; color: #6B7280;'>• Enforced AST SELECT-only dry-run validation.</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='border-bottom: 1px solid #E5E7EB; margin: 1.5rem 0;'></div>", unsafe_allow_html=True)

    # 6. Results Data Table
    st.markdown(f"##### 🗄️ Query Results ({row_count} rows)")
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.write("No result rows returned.")

    # 7. KPI Metadata Cards
    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    col1.metric("Rows Returned", f"{row_count:,}")
    col2.metric("Bytes Scanned", f"{bytes_scanned / (1024 * 1024):,.2f} MB" if bytes_scanned else "0 MB")
    col3.metric("Slot Execution", f"{slot_ms:,} ms" if slot_ms else "0 ms")

    st.markdown("<div style='border-bottom: 1px solid #E5E7EB; margin: 1.5rem 0;'></div>", unsafe_allow_html=True)

    # 8. Export Toolbar
    st.markdown("##### 📥 Export & Audit Actions")
    col_pdf, col_md, col_rerun = st.columns([1, 1, 1])

    with col_pdf:
        try:
            pdf_bytes = generate_report_pdf(
                question=question,
                answer=answer,
                sql=sql,
                rows=rows,
                routing_path=routing_path,
                timestamp=executed_at,
                guardrails=guardrails,
                provenance=provenance,
                bytes_scanned=bytes_scanned,
                row_count=row_count,
            )
            filename = f"report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            st.download_button(
                label="📄 Download PDF Report",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
                key="btn_download_pdf",
                use_container_width=True,
            )
        except Exception as pdf_err:
            st.error(f"Could not generate PDF: {pdf_err}")

    md_content = format_markdown_report(
        question=question,
        answer=answer,
        sql=sql,
        rows=rows,
        routing_path=routing_path,
        timestamp=executed_at,
        guardrails=guardrails,
        provenance=provenance,
        bytes_scanned=bytes_scanned,
        row_count=row_count,
    )
    with col_md:
        st.download_button(
            label="📝 Copy Markdown",
            data=md_content,
            file_name="analytical_report.md",
            mime="text/markdown",
            key="btn_download_md",
            use_container_width=True,
        )

    with col_rerun:
        if st.button("🔄 Re-run Live Query", key="btn_rerun_query", use_container_width=True):
            st.session_state.rerun_triggered = True

    # Reproducibility Verification
    if st.session_state.get("rerun_triggered"):
        st.markdown("##### 🔍 Re-run Reproducibility Result")
        with st.spinner("Re-executing query against BigQuery warehouse..."):
            try:
                from pwa.agent.pipeline.orchestrator import run_query_verbose

                new_res = run_query_verbose(question)
                if isinstance(new_res, str):
                    st.write(f"Re-run returned notice: {new_res}")
                else:
                    new_rows = new_res.rows or []
                    orig_rows = rows or []

                    if new_rows == orig_rows:
                        st.markdown(
                            """
                            <div style="background: #F4F4F5; border: 1px solid #CED4DA; border-radius: 6px; padding: 0.75rem 1rem; font-size: 0.85rem; color: #111827;">
                                ✅ <b>Reproducibility Verified</b>: Re-executed warehouse query matches deliverable data exactly.
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            """
                            <div style="background: #F4F4F5; border: 1px solid #CED4DA; border-radius: 6px; padding: 0.75rem 1rem; font-size: 0.85rem; color: #111827;">
                                ℹ️ <b>Data Refresh Detected</b>: Fresh warehouse re-run returned updated row snapshot.
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
            except Exception as rerun_exc:
                st.error(f"Re-execution failed: {rerun_exc}")
