"""PDF export generator for PWA Analytical Deliverables using fpdf2."""

import logging
from typing import Optional
from fpdf import FPDF

logger = logging.getLogger("pwa.ui.pdf_export")


class PDFReport(FPDF):
    """Custom FPDF layout with running header and footer."""

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "PWA Analytical Deliverable Report", border=False, align="L")
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", border=False, align="C")


def generate_report_pdf(
    question: str,
    answer: str,
    sql: Optional[str] = None,
    rows: Optional[list[dict]] = None,
    routing_path: str = "template-match",
    timestamp: str = "",
    guardrails: Optional[list[dict]] = None,
    provenance: Optional[list[dict]] = None,
    bytes_scanned: Optional[int] = 0,
    row_count: int = 0,
) -> bytes:
    """Generate styled PDF document for an analytical report deliverable."""
    pdf = PDFReport()
    pdf.alias_nb_pages()
    pdf.add_page()

    # Title & Metadata
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(20, 20, 20)
    pdf.multi_cell(0, 7, f"Report: {question}")
    pdf.ln(3)

    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(100, 100, 100)
    scanned_str = f"{bytes_scanned or 0:,}"
    pdf.cell(
        0,
        5,
        f"Executed: {timestamp} | Path: {routing_path} | Rows: {row_count} | Bytes Scanned: {scanned_str}",
    )
    pdf.ln(5)

    # Headline Finding
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 6, "Headline Finding:")
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(30, 30, 30)
    pdf.multi_cell(0, 5, answer)
    pdf.ln(5)

    # Data Provenance
    if provenance:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 6, "Data Provenance:")
        pdf.ln(6)
        pdf.set_font("Helvetica", "", 8.5)
        for item in provenance:
            t_name = item.get("table_name", "Unknown")
            refreshed = item.get("last_refreshed", "")
            t_type = item.get("type", "")
            pdf.cell(0, 5, f"  - Table: {t_name} ({t_type}) | Last Refreshed: {refreshed}")
            pdf.ln(5)
        pdf.ln(4)

    # Guardrails / Filters Applied
    if guardrails:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 6, "Guardrails & Filters Applied:")
        pdf.ln(6)
        pdf.set_font("Helvetica", "", 8.5)
        for g in guardrails:
            g_name = g.get("name", "Guardrail")
            g_desc = g.get("description", "")
            pdf.multi_cell(0, 4.5, f"  - [{g_name}]: {g_desc}")
        pdf.ln(4)

    # Executed SQL Code Block
    if sql:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 6, "Executed Methodology SQL:")
        pdf.ln(6)
        pdf.set_font("Courier", "", 8)
        pdf.set_fill_color(245, 245, 245)
        pdf.multi_cell(0, 4, sql, fill=True)
        pdf.ln(5)

    # Results Table
    if rows and len(rows) > 0:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 6, f"Full Results Table ({len(rows)} rows):")
        pdf.ln(8)


        cols = list(rows[0].keys())
        printable_width = 190.0
        col_width = max(18.0, printable_width / len(cols))

        # Header row
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(230, 230, 230)
        for c in cols:
            pdf.cell(col_width, 6, str(c)[:14], border=1, fill=True)
        pdf.ln()

        # Data rows (top 50)
        pdf.set_font("Helvetica", "", 8)
        for row in rows[:50]:
            for c in cols:
                val = str(row.get(c, ""))
                pdf.cell(col_width, 6, val[:18], border=1)
            pdf.ln()

    return bytes(pdf.output())
