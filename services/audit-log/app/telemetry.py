"""OpenTelemetry-ready structure.

This module provides a placeholder for OpenTelemetry instrumentation.
In future phases, add:
  from opentelemetry import trace
  from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
  from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
  from opentelemetry.sdk.trace import TracerProvider
  from opentelemetry.sdk.trace.export import BatchSpanProcessor
"""

from __future__ import annotations


def setup_telemetry(service_name: str) -> None:
    """Configure OpenTelemetry for the audit service. Placeholder for future instrumentation."""
    _ = service_name
