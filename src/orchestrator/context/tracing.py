"""Configure an optional process-wide OpenTelemetry OTLP exporter."""

import atexit
from typing import Any

from opentelemetry import trace


_provider: Any | None = None


def configure_tracing(endpoint: str) -> Any | None:
    global _provider
    if not endpoint or _provider is not None:
        return _provider
    current_provider = trace.get_tracer_provider()
    if current_provider.__class__.__name__ != "ProxyTracerProvider":
        return None

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": "orchestrator"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    _provider = provider
    atexit.register(provider.shutdown)
    return provider
