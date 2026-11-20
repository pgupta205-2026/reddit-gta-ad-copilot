"""OpenTelemetry distributed tracing setup for local dev and Google Cloud Trace.

Links parent invocation spans across ADK coordinator routing, parallel sub-agent
execution, tool calls, PII redaction, and async memory consolidation.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from app.observability.logging import get_logger

_LOGGER = get_logger(__name__)
_TRACING_INITIALIZED = False


class _NoOpSpan:
    """Fallback span used only if opentelemetry-sdk is unavailable."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: ARG002
        return None

    def record_exception(self, exc: BaseException) -> None:  # noqa: ARG002
        return None


class _NoOpTracer:
    """Fallback tracer preserving uniform context-manager ergonomics."""

    @contextmanager
    def start_as_current_span(
        self, name: str, attributes: dict[str, Any] | None = None  # noqa: ARG002
    ) -> Iterator[_NoOpSpan]:
        yield _NoOpSpan()


def configure_tracing(
    service_name: str = "reddit-gta-ad-copilot",
    *,
    gcp_project_id: str | None = None,
    exporter_mode: str = "console",
    disabled: bool = False,
) -> Any:
    """Configure OpenTelemetry TracerProvider with GCP Cloud Trace or local exporter.

    Args:
        service_name: OpenTelemetry `service.name` resource attribute.
        gcp_project_id: Target GCP project ID when exporting to Cloud Trace.
        exporter_mode: One of "google_cloud_trace", "console", "memory", or "none".
        disabled: If True, leaves tracing as a no-op provider.

    Returns:
        Configured OpenTelemetry tracer (or fallback tracer if SDK unavailable).
    """
    global _TRACING_INITIALIZED
    if disabled:
        return _NoOpTracer()

    try:
        from opentelemetry import trace  # type: ignore[import-untyped]
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-untyped]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-untyped]
        from opentelemetry.sdk.trace.export import (  # type: ignore[import-untyped]
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )

        if not _TRACING_INITIALIZED:
            resource = Resource.create({"service.name": service_name})
            provider = TracerProvider(resource=resource)

            if exporter_mode == "google_cloud_trace" and gcp_project_id:
                try:
                    from opentelemetry.exporter.cloud_trace import (  # type: ignore[import-untyped]
                        CloudTraceSpanExporter,
                    )

                    exporter = CloudTraceSpanExporter(project_id=gcp_project_id)
                    provider.add_span_processor(BatchSpanProcessor(exporter))
                except Exception as exc:
                    _LOGGER.warning(
                        "otel_cloud_trace_exporter_fallback",
                        error=str(exc),
                        fallback="console",
                    )
                    provider.add_span_processor(
                        SimpleSpanProcessor(ConsoleSpanExporter())
                    )
            elif exporter_mode == "console":
                provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

            trace.set_tracer_provider(provider)
            _TRACING_INITIALIZED = True
            _LOGGER.info(
                "otel_tracing_configured",
                service_name=service_name,
                exporter_mode=exporter_mode,
            )

        return trace.get_tracer(service_name)
    except ImportError:
        return _NoOpTracer()


def get_tracer(name: str = "reddit-gta-ad-copilot") -> Any:
    """Return an OpenTelemetry tracer bound to `name`."""
    try:
        from opentelemetry import trace  # type: ignore[import-untyped]

        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


@contextmanager
def traced_span(
    span_name: str,
    attributes: dict[str, Any] | None = None,
    *,
    tracer_name: str = "reddit-gta-ad-copilot",
) -> Iterator[Any]:
    """Context manager creating a linked OpenTelemetry child span."""
    tracer = get_tracer(tracer_name)
    with tracer.start_as_current_span(span_name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span
