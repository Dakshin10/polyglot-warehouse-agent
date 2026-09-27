"""Unit tests verifying pipeline failure alerting and non-zero exit codes."""

from unittest.mock import MagicMock, patch
from pwa.run_bigquery import run_warehouse_pipeline
from pwa.run_source import run_source_pipeline


def test_source_pipeline_dispatches_alert_on_failure():
    with (
        patch(
            "pwa.preprocessing.adventureworks_ingest.ingest_adventureworks", side_effect=RuntimeError("DB Conn Error")
        ),
        patch("pwa.observability.alerting.default_alert_sinks") as mock_sinks_fn,
    ):
        mock_sink = MagicMock()
        mock_sinks_fn.return_value = mock_sink

        ok = run_source_pipeline(source_name="adventureworks")
        assert ok is False
        assert mock_sink.send.called
        alert_sent = mock_sink.send.call_args[0][0]
        assert alert_sent.alert_type == "PIPELINE_FAILURE"
        assert alert_sent.severity == "CRITICAL"


def test_warehouse_pipeline_dispatches_alert_on_failure():
    with (
        patch("pwa.preprocessing.bigquery_setup.run_setup", side_effect=RuntimeError("BQ Setup Error")),
        patch("pwa.observability.alerting.default_alert_sinks") as mock_sinks_fn,
    ):
        mock_sink = MagicMock()
        mock_sinks_fn.return_value = mock_sink

        ok = run_warehouse_pipeline()
        assert ok is False
        assert mock_sink.send.called
        alert_sent = mock_sink.send.call_args[0][0]
        assert alert_sent.alert_type == "PIPELINE_FAILURE"
        assert alert_sent.severity == "CRITICAL"
