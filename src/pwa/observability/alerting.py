"""Alerting abstractions and notification sinks.

Configuration
-------------
PWA_SLACK_WEBHOOK_URL       Slack incoming-webhook URL. When set, SlackAlertSink
                            posts every alert there.
PWA_PAGERDUTY_ROUTING_KEY   PagerDuty Events API v2 routing key. When set,
                            PagerDutyAlertSink triggers an incident for every
                            CRITICAL/HIGH alert (paging on MEDIUM/LOW would be
                            alert-fatigue, not safety).

Neither sink is required: `default_alert_sinks()` always includes the log
sink, and adds the webhook sinks only when their env var is configured, so a
missing webhook degrades to "logged but not paged," never a crash.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("pwa.observability.alerting")


@dataclass
class PipelineAlert:
    """Structure for pipeline alerts."""

    alert_type: str  # QUALITY_FAILURE | RECONCILIATION_MISMATCH | SCHEMA_DRIFT | PIPELINE_FAILURE | STALE_DATA
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW
    source_id: str
    table_name: str | None
    message: str
    run_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AlertSink(ABC):
    """Abstract base class for alert notification sinks."""

    @abstractmethod
    def send(self, alert: PipelineAlert) -> bool:
        """Send a pipeline alert notification."""
        pass


class LogAlertSink(AlertSink):
    """Alert sink emitting structured alert events to standard logging streams."""

    def send(self, alert: PipelineAlert) -> bool:
        msg = (
            f"[ALERT:{alert.alert_type}] severity={alert.severity} "
            f"source={alert.source_id} table={alert.table_name} "
            f"run_id={alert.run_id}: {alert.message}"
        )
        if alert.severity in ("CRITICAL", "HIGH"):
            logger.error(msg)
        else:
            logger.warning(msg)
        return True


class SlackAlertSink(AlertSink):
    """Posts alerts to a Slack channel via an incoming webhook URL."""

    def __init__(self, webhook_url: str, timeout_seconds: float = 5.0) -> None:
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds

    def send(self, alert: PipelineAlert) -> bool:
        import requests

        emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "⚪"}.get(alert.severity, "⚪")
        text = (
            f"{emoji} *[{alert.alert_type}]* severity=`{alert.severity}` "
            f"source=`{alert.source_id}` table=`{alert.table_name or '-'}`\n"
            f"{alert.message}"
        )
        try:
            resp = requests.post(self.webhook_url, json={"text": text}, timeout=self.timeout_seconds)
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error(f"[SlackAlertSink] Failed to deliver alert: {exc}")
            return False


class PagerDutyAlertSink(AlertSink):
    """Triggers a PagerDuty incident via the Events API v2 for CRITICAL/HIGH alerts.

    MEDIUM/LOW alerts are intentionally not paged — routing everything to an
    on-call phone is how alerting systems get muted or ignored.
    """

    _EVENTS_API_URL = "https://events.pagerduty.com/v2/enqueue"

    def __init__(self, routing_key: str, timeout_seconds: float = 5.0) -> None:
        self.routing_key = routing_key
        self.timeout_seconds = timeout_seconds

    def send(self, alert: PipelineAlert) -> bool:
        if alert.severity not in ("CRITICAL", "HIGH"):
            return True

        import requests

        payload: dict[str, Any] = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "dedup_key": f"pwa-{alert.alert_type}-{alert.source_id}-{alert.table_name or 'none'}",
            "payload": {
                "summary": f"[{alert.alert_type}] {alert.source_id}/{alert.table_name or '-'}: {alert.message}",
                "severity": "critical" if alert.severity == "CRITICAL" else "error",
                "source": alert.source_id,
                "custom_details": {
                    "run_id": alert.run_id,
                    "table_name": alert.table_name,
                    "timestamp": alert.timestamp,
                },
            },
        }
        try:
            resp = requests.post(self._EVENTS_API_URL, json=payload, timeout=self.timeout_seconds)
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error(f"[PagerDutyAlertSink] Failed to deliver alert: {exc}")
            return False


class CompositeAlertSink(AlertSink):
    """Fans an alert out to every configured sink; never lets one sink's
    failure suppress delivery to the others."""

    def __init__(self, sinks: list[AlertSink]) -> None:
        self.sinks = sinks

    def send(self, alert: PipelineAlert) -> bool:
        results = []
        for sink in self.sinks:
            try:
                results.append(sink.send(alert))
            except Exception as exc:
                logger.error(f"[CompositeAlertSink] Sink {type(sink).__name__} raised: {exc}")
                results.append(False)
        return all(results)


def validate_alerting_config(strict: bool = False) -> bool:
    """Validate alerting configuration.

    If strict is True (or PWA_ALERTING_STRICT=1), raises ValueError if neither
    PWA_SLACK_WEBHOOK_URL nor PWA_PAGERDUTY_ROUTING_KEY is configured.
    """
    slack_url = os.getenv("PWA_SLACK_WEBHOOK_URL", "").strip()
    pagerduty_key = os.getenv("PWA_PAGERDUTY_ROUTING_KEY", "").strip()
    strict_env = os.getenv("PWA_ALERTING_STRICT", "0").strip() in ("1", "true", "TRUE")

    is_strict = strict or strict_env

    if is_strict and not (slack_url or pagerduty_key):
        raise ValueError(
            "PWA_ALERTING_STRICT is enabled but neither PWA_SLACK_WEBHOOK_URL "
            "nor PWA_PAGERDUTY_ROUTING_KEY is configured."
        )
    return True


def default_alert_sinks() -> CompositeAlertSink:
    """Build the alert sink configured for this environment.

    Always includes LogAlertSink. Adds SlackAlertSink / PagerDutyAlertSink
    only when their respective env var is set, so a fresh clone with no
    webhooks configured still logs alerts instead of raising on startup.
    """
    validate_alerting_config()

    sinks: list[AlertSink] = [LogAlertSink()]

    slack_url = os.getenv("PWA_SLACK_WEBHOOK_URL", "").strip()
    if slack_url:
        sinks.append(SlackAlertSink(slack_url))

    pagerduty_key = os.getenv("PWA_PAGERDUTY_ROUTING_KEY", "").strip()
    if pagerduty_key:
        sinks.append(PagerDutyAlertSink(pagerduty_key))

    return CompositeAlertSink(sinks)
