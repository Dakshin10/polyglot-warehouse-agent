"""Unit tests for Streamlit chat-thread UI components and orchestrator integration."""

from unittest.mock import MagicMock, patch

from app import _stub_run_query_verbose
from pwa.agent.pipeline.orchestrator import PipelineResult
from pwa.ui.components.answer_panel import render_answer_panel
from pwa.ui.components.evidence_panel import _format_bytes, render_evidence_panel
from pwa.ui.components.header import render_header
from pwa.ui.components.history_panel import render_history_panel
from pwa.ui.components.rejection_panel import render_rejection_panel
from pwa.ui.components.stage_tracker import (
    render_pipeline_trace_expander,
    render_thinking_status,
)
from pwa.ui.styles import apply_custom_styles


def test_format_bytes():
    """Test byte formatting helper."""
    assert _format_bytes(None) == "0 B (Cached / Schema only)"
    assert _format_bytes(500) == "500 B"
    assert _format_bytes(1048576) == "1.0 MB"
    assert _format_bytes(1073741824) == "1.00 GB"


def test_stub_run_query_verbose():
    """Test stub runner emits correct PipelineResult and triggers callbacks."""
    callback_calls = []

    def _cb(stage, status, extra):
        callback_calls.append((stage, status))

    res = _stub_run_query_verbose("test question", stage_callback=_cb)

    assert isinstance(res, PipelineResult)
    assert "Total sales revenue" in res.answer
    assert res.row_count == 4
    assert len(callback_calls) == 8  # 4 stages * 2 events (started, completed)


@patch("streamlit.markdown")
def test_component_renders(mock_markdown):
    """Test rendering UI components produces HTML without throwing errors."""
    apply_custom_styles()
    assert mock_markdown.called

    render_header()
    render_thinking_status("grounding")
    render_answer_panel("Total sales revenue was $1.2M in 2011.")
    render_rejection_panel("Static SQL Validation Failed", "DROP TABLE test;")
    render_history_panel(["what was the total sales revenue in 2014?"])


@patch("streamlit.expander")
@patch("streamlit.code")
@patch("streamlit.dataframe")
def test_evidence_panel(mock_df, mock_code, mock_expander):
    """Test evidence panel renders expanders for SQL, data, and metadata."""
    res = PipelineResult(
        answer="Total sales revenue was $5.1M in 2014.",
        sql="SELECT * FROM mart.v_sales_order_line;",
        rows=[{"order_year": 2014, "total_sales": 5100000.0}],
        bytes_scanned=1000,
        stage_latencies={"sql": 0.5},
        row_count=1,
    )
    mock_expander.return_value.__enter__ = MagicMock()
    mock_expander.return_value.__exit__ = MagicMock()

    render_pipeline_trace_expander({"sql": 0.5})
    render_evidence_panel(res)
    assert mock_code.called
