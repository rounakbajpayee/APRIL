"""
runtime_trace.py — Canonical runtime trace infrastructure for APRIL.

Using OpenTelemetry.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

# ---------------------------------------------------------------------------
# Severity level constants
# ---------------------------------------------------------------------------

DEBUG = "DEBUG"
INFO = "INFO"
WARNING = "WARNING"
ERROR = "ERROR"
CRITICAL = "CRITICAL"

# Initialize OpenTelemetry Global TracerProvider if not already configured
if not isinstance(trace.get_tracer_provider(), TracerProvider):
    provider = TracerProvider()
    processor = SimpleSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

_tracer = trace.get_tracer("april.runtime_trace")


def get_tracer() -> trace.Tracer:
    """Return the global tracer."""
    return _tracer


def trace_marker(message: str) -> None:
    """Emit a marker by starting and immediately ending a span."""
    try:
        with _tracer.start_as_current_span(message):
            pass
    except Exception:
        pass


def trace_event(
    event: str,
    *,
    subsystem: str,
    severity: str = INFO,
    request_id: str | None = None,
    job_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """
    Emit a structured trace event using OpenTelemetry.
    Starts a brief span and adds an event to it with attributes.
    """
    try:
        attributes = {
            "subsystem": subsystem,
            "severity": severity,
            "thread_name": threading.current_thread().name,
        }
        if request_id:
            attributes["request_id"] = request_id
        if job_id:
            attributes["job_id"] = job_id
        if payload:
            try:
                # Convert payload to string for OTel attributes
                attributes["payload"] = json.dumps(payload, ensure_ascii=False)
            except Exception:
                pass

        with _tracer.start_as_current_span(event, attributes=attributes) as span:
            span.add_event(event, attributes=attributes)
    except Exception:
        pass


def flush(timeout: float = 3.0) -> None:
    """Flush pending OTel spans."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(int(timeout * 1000))


def shutdown(timeout: float = 3.0) -> None:
    """Shutdown OTel processor."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()
