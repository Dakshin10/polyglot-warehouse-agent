"""Unit tests for real alert sinks (Slack/PagerDuty) and control-plane alert wiring."""

from unittest.mock import MagicMock, patch

from pwa.observability.alerting import (
    CompositeAlertSink,
    LogAlertSink,
    PagerDutyAlertSink,
    PipelineAlert,
    SlackAlertSink,
    default_alert_sinks,
)


def _alert(severity: str = "HIGH") -> PipelineAlert:
    return PipelineAlert(
        alert_type="QUALITY_FAILURE",
        severity=severity,
        source_id="adventureworks",
        table_name="sales_order_header",
        message="Null constraint violated on sales_order_id.",
        run_id="run-123",
    )


def test_log_alert_sink_always_succeeds():
    assert LogAlertSink().send(_alert()) is True


def test_slack_alert_sink_posts_webhook():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    with patch("requests.post", return_value=mock_resp) as mock_post:
        sink = SlackAlertSink("https://hooks.slack.test/webhook")
        assert sink.send(_alert()) is True
        mock_post.assert_called_once()
        assert mock_post.call_args.kwargs["json"]["text"]


def test_slack_alert_sink_failure_returns_false():
    with patch("requests.post", side_effect=RuntimeError("network down")):
        sink = SlackAlertSink("https://hooks.slack.test/webhook")
        assert sink.send(_alert()) is False


def test_pagerduty_sink_pages_only_high_and_critical():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    with patch("requests.post", return_value=mock_resp) as mock_post:
        sink = PagerDutyAlertSink("routing-key-123")

        assert sink.send(_alert(severity="MEDIUM")) is True
        mock_post.assert_not_called()

        assert sink.send(_alert(severity="CRITICAL")) is True
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        assert payload["routing_key"] == "routing-key-123"
        assert payload["payload"]["severity"] == "critical"


def test_composite_sink_fans_out_and_survives_one_failure():
    good_sink = MagicMock()
    good_sink.send.return_value = True
    bad_sink = MagicMock()
    bad_sink.send.side_effect = RuntimeError("boom")

    composite = CompositeAlertSink([good_sink, bad_sink])
    result = composite.send(_alert())

    assert result is False  # one sink failed
    good_sink.send.assert_called_once()
    bad_sink.send.assert_called_once()


def test_default_alert_sinks_always_includes_log_sink():
    with patch.dict("os.environ", {}, clear=True):
        composite = default_alert_sinks()
        assert any(isinstance(s, LogAlertSink) for s in composite.sinks)
        assert len(composite.sinks) == 1  # no webhooks configured


def test_default_alert_sinks_adds_slack_when_configured():
    with patch.dict("os.environ", {"PWA_SLACK_WEBHOOK_URL": "https://hooks.slack.test/x"}, clear=True):
        composite = default_alert_sinks()
        assert any(isinstance(s, SlackAlertSink) for s in composite.sinks)
