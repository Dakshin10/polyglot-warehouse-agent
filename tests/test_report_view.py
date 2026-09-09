"""Unit tests for Report View components, PDF export, and Markdown formatting."""

from pwa.ui.components.report_view import format_markdown_report
from pwa.ui.pdf_export import generate_report_pdf


def test_format_markdown_report():
    question = "Which director has the highest average ROI?"
    answer = "Steven Spielberg has the highest average ROI of 4.50x across 12 movies."
    sql = "SELECT director_name, avg_roi FROM rollup.avg_roi_by_director ORDER BY avg_roi DESC LIMIT 1;"
    rows = [{"director_name": "Steven Spielberg", "avg_roi": 4.5}]
    routing_path = "template-match"
    timestamp = "2026-09-09 12:00:00 UTC"
    guardrails = [
        {
            "name": "ROI Guard",
            "description": "Excluded films with budget_usd <= $1,000 (11 films) to prevent divide-by-near-zero ROI distortion",
        }
    ]
    provenance = [
        {"table_name": "rollup.avg_roi_by_director", "type": "rollup", "last_refreshed": "2026-09-09 07:00:00 UTC"}
    ]

    md = format_markdown_report(
        question=question,
        answer=answer,
        sql=sql,
        rows=rows,
        routing_path=routing_path,
        timestamp=timestamp,
        guardrails=guardrails,
        provenance=provenance,
        bytes_scanned=1048576,
        row_count=1,
    )

    assert "Analytical Deliverable Report: Which director has the highest average ROI?" in md
    assert "Steven Spielberg" in md
    assert "SELECT director_name" in md
    assert "rollup.avg_roi_by_director" in md
    assert "Excluded films with budget_usd <= $1,000" in md


def test_generate_report_pdf():
    question = "Top 3 highest grossing movies"
    answer = "The top movies are Avatar, Endgame, and Titanic."
    sql = "SELECT title, revenue FROM mart.v_movie ORDER BY revenue DESC LIMIT 3;"
    rows = [
        {"title": "Avatar", "revenue": 2923706026},
        {"title": "Avengers: Endgame", "revenue": 2797501328},
        {"title": "Titanic", "revenue": 2264162310},
    ]

    pdf_bytes = generate_report_pdf(
        question=question,
        answer=answer,
        sql=sql,
        rows=rows,
        routing_path="template-match",
        timestamp="2026-09-09 12:00:00 UTC",
        bytes_scanned=5242880,
        row_count=3,
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")
