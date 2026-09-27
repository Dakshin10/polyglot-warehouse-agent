"""Unit tests for Phase 5 UI exception handling."""

from unittest.mock import patch
import pandas as pd
from pwa.ui.components.evidence_panel import render_evidence_panel
from pwa.ui.components.viz_panel import render_viz_panel


def test_evidence_panel_handles_viz_rendering_error():
    result = {
        "sql": "SELECT 1",
        "rows": [{"a": 1}],
        "bytes_scanned": 1024,
        "count": 1,
    }

    # Force render_viz_panel to raise an exception inside render_evidence_panel
    with (
        patch("pwa.ui.components.viz_panel.render_viz_panel", side_effect=ValueError("Test Viz Error")),
        patch("streamlit.warning") as mock_warning,
    ):
        render_evidence_panel(result, question="Test question", msg_idx=0)
        assert mock_warning.called
        assert "Test Viz Error" in mock_warning.call_args[0][0]


def test_viz_panel_handles_recommendation_error():
    df = pd.DataFrame([{"col1": 1}])
    with (
        patch("pwa.ui.viz_recommendation.build_from_shape", side_effect=RuntimeError("Shape build failed")),
        patch("streamlit.caption") as mock_caption,
    ):
        render_viz_panel(df, recommendation_dict=None, msg_idx=0, question="test")
        assert mock_caption.called
        assert "Shape build failed" in mock_caption.call_args[0][0]
