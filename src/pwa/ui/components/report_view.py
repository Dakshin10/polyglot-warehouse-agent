"""Streamlit component for rendering the PWA Analytical Deliverable Report View."""

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
        "## Headline Finding",
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
            "## Guardrails & Rules Applied",
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
            f"## Full Results Table ({row_count} rows)",
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
        stage_details.get("routing_path", "LLM-fallback") if isinstance(stage_details, dict) else "LLM-fallback"
    )
    executed_at = (
        getattr(result, "executed_at", None)
        or report_data.get("timestamp")
        or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )

    guardrails = getattr(result, "guardrails_applied", []) or report_data.get("guardrails_applied", [])
    provenance = getattr(result, "data_provenance", []) or report_data.get("data_provenance", [])

    # Navigation & Action Header
    col_nav, col_actions = st.columns([1, 1])
    with col_nav:
        if st.button("← Back to Chat Thread", key="btn_back_to_chat"):
            st.session_state.active_view = "chat"
            st.rerun()

    with col_actions:
        st.caption(f"📍 Mode: **Report Deliverable View** (`{routing_path}`)")

    st.divider()

    # 2a. Header
    st.subheader(f"📊 Report: {question}")
    st.caption(f"⏱️ Executed: `{executed_at}` | ⚡ Routing Path: `{routing_path}`")

    # 2b. Headline Number / Finding + Primary Chart
    st.markdown("### 💡 Headline Finding")
    st.info(answer)

    if rows:
        df = pd.DataFrame(rows)
        render_viz_panel(df, viz_rec, msg_idx=999, question=question)

    st.divider()

    # 2c. Methodology Block (collapsible but expanded by default)
    with st.expander("🔬 Methodology & Executed SQL", expanded=True):
        if sql:
            st.code(sql, language="sql")
        else:
            st.write("No SQL query recorded for this deliverable.")

    # 2d. Data Provenance Block
    with st.container():
        st.markdown("### 🛡️ Data Provenance")
        if provenance:
            for p in provenance:
                t_name = p.get("table_name", "Unknown Table")
                t_type = p.get("type", "table")
                t_desc = p.get("description", "")
                t_refresh = p.get("last_refreshed", "Unknown")
                st.markdown(f"- **`{t_name}`** (`{t_type}`): {t_desc} — *Last Refreshed*: `{t_refresh}`")
        else:
            st.write("- Query executed against base warehouse views over live transactional tables.")

    # 2e. Guardrails & Filters Applied
    with st.container():
        st.markdown("### 🛑 Guardrails & Filters Applied")
        if guardrails:
            for g in guardrails:
                st.markdown(f"- **[{g.get('name')}]**: {g.get('description')} (*Rule: `{g.get('rule')}`*)")
        else:
            st.write("- Standard AST read-only validation & cost dry-run limit applied.")

    # 2f. Full Results Table
    st.markdown(f"### 🗄️ Full Results Table ({row_count} rows)")
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.write("No result rows returned.")

    # 2g. Diagnostic Details
    col1, col2, col3 = st.columns(3)
    col1.metric("Rows Returned", f"{row_count:,}")
    col2.metric("Bytes Scanned", f"{bytes_scanned / (1024 * 1024):,.2f} MB" if bytes_scanned else "0 MB")
    col3.metric("Slot MS", f"{slot_ms:,}" if slot_ms else "N/A")

    st.divider()

    # 3. Export & 4. Reproducibility Bar
    st.markdown("### 📥 Export & Reproducibility Actions")
    col_pdf, col_md, col_rerun = st.columns([1, 1, 1])

    # PDF Download
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
                label="📄 Download as PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
                key="btn_download_pdf",
            )
        except Exception as pdf_err:
            st.error(f"Could not generate PDF: {pdf_err}")

    # Copy / Download Markdown
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
            label="📝 Copy as Markdown",
            data=md_content,
            file_name="analytical_report.md",
            mime="text/markdown",
            key="btn_download_md",
        )

    # Re-run query & diff action
    with col_rerun:
        if st.button("🔄 Re-run this query", key="btn_rerun_query"):
            st.session_state.rerun_triggered = True

    # Reproducibility Diff Output Block
    if st.session_state.get("rerun_triggered"):
        st.markdown("#### 🔍 Re-run Reproducibility Verification")
        with st.spinner("Re-executing query against live warehouse data..."):
            try:
                from pwa.agent.pipeline.orchestrator import run_query_verbose

                new_res = run_query_verbose(question)

                if isinstance(new_res, str):
                    st.warning(f"Re-run returned notice: {new_res}")
                else:
                    new_rows = new_res.rows or []
                    orig_rows = rows or []

                    if new_rows == orig_rows:
                        st.success(
                            "✅ Reproducibility Verified: Re-executed numbers match original report deliverable exactly."
                        )
                    else:
                        st.warning("⚠️ Data Refresh Detected: Re-executed results differ from original deliverable!")
                        col_d1, col_d2 = st.columns(2)
                        with col_d1:
                            st.caption("Original Report Results")
                            st.dataframe(pd.DataFrame(orig_rows), use_container_width=True)
                        with col_d2:
                            st.caption("Fresh Re-run Results")
                            st.dataframe(pd.DataFrame(new_rows), use_container_width=True)
            except Exception as rerun_exc:
                st.error(f"Re-execution failed: {rerun_exc}")
