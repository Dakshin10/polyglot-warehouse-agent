"""OpenTelemetry tracing setup for the PWA query pipeline.

Every pipeline stage already measures its own latency into a dict that the
caller prints once and discards — no metric or trace ever leaves the process,
so there is no way to see P95 latency, per-stage cost, or a slow trace across
a fleet of instances. This module makes each stage a real exported span
instead, without changing anything about the existing `stage_latencies` dict
(callers, tests, and the CLI/UI keep working exactly as before).

Configuration
-------------
PWA_OTEL_ENABLED                Set to "1" to enable tracing at all (default:
                                 disabled — a query engine with no configured
                                 exporter shouldn't pay tracing overhead).
PWA_OTEL_CONSOLE_EXPORT          Set to "1" to also print spans to stdout
                                 (useful for local development).
OTEL_EXPORTER_OTLP_ENDPOINT      Standard OTel env var. When set, spans are
                                 exported to this OTLP HTTP collector (Grafana
                                 Tempo, Honeycomb, Jaeger, etc.). Requires the
                                 optional `opentelemetry-exporter-otlp-proto-http`
                                 package — falls back to a warning (not a
                                 crash) if it isn't installed.

If neither exporter is configured, tracing still runs (spans are created and
immediately dropped by a no-op processor) so instrumentation code paths are
identical in every environment.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger("pwa.observability.tracing")

_TRACER_NAME = "pwa.pipeline"
_initialized = False


def _is_enabled() -> bool:
    return os.getenv("PWA_OTEL_ENABLED", "0").strip() == "1"


def configure_tracing() -> None:
    """Idempotently configure the global TracerProvider. Safe to call repeatedly."""
    global _initialized
    if _initialized or not _is_enabled():
        return

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider

    provider = TracerProvider(resource=Resource.create({"service.name": "polyglot-warehouse-agent"}))

    if os.getenv("PWA_OTEL_CONSOLE_EXPORT", "0").strip() == "1":
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
            logger.info(f"[Tracing] Exporting spans to OTLP collector at {otlp_endpoint}")
        except ImportError:
            logger.warning(
                "OTEL_EXPORTER_OTLP_ENDPOINT is set but the 'opentelemetry-exporter-otlp-proto-http' "
                "package is not installed (pip install polyglot-warehouse-agent[observability]) — "
                "spans will not be exported to it."
            )

    trace.set_tracer_provider(provider)
    _initialized = True


@contextmanager
def traced_stage(name: str, **attributes: Any) -> Iterator[None]:
    """Wrap a pipeline stage in a span named `pwa.pipeline.<name>`.

    A complete no-op (zero overhead beyond one attribute check) unless
    PWA_OTEL_ENABLED=1 — this is safe to leave wrapped around every stage
    unconditionally.
    """
    if not _is_enabled():
        yield
        return

    configure_tracing()
    from opentelemetry import trace

    tracer = trace.get_tracer(_TRACER_NAME)
    with tracer.start_as_current_span(f"pwa.pipeline.{name}") as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
        yield
