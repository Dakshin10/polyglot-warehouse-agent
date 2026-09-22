"""Unit tests for OpenTelemetry tracing wiring (opt-in, zero-overhead when disabled)."""

from unittest.mock import patch

from pwa.observability.tracing import traced_stage


def test_traced_stage_is_noop_when_disabled():
    """Default (PWA_OTEL_ENABLED unset) must not touch opentelemetry at all."""
    with patch.dict("os.environ", {}, clear=True):
        with traced_stage("some_stage", foo="bar"):
            executed = True
    assert executed is True


def test_traced_stage_creates_a_real_span_when_enabled():
    with patch.dict("os.environ", {"PWA_OTEL_ENABLED": "1"}, clear=True):
        with traced_stage("grounding", question_length=42):
            executed = True
    assert executed is True


def test_traced_stage_propagates_exceptions():
    with patch.dict("os.environ", {"PWA_OTEL_ENABLED": "1"}, clear=True):
        try:
            with traced_stage("execution"):
                raise ValueError("boom")
        except ValueError as exc:
            assert str(exc) == "boom"
        else:
            raise AssertionError("expected ValueError to propagate")
