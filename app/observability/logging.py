"""Structured JSON logging with GCP Cloud Logging trace correlation & PII scrubbing.

All application modules must use `get_logger(__name__)` rather than bare
`print()` statements. Every log event is emitted as a single-line JSON record
containing ISO-8601 timestamp, Cloud Logging severity, active OpenTelemetry
trace/span IDs, and PII-redacted structured fields.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import MutableMapping
from datetime import UTC, datetime
from typing import Any

from app.security.pii_redactor import PiiRedactor

try:
    import structlog  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - stdlib JSON fallback when structlog absent
    structlog = None  # type: ignore[assignment]

_SHARED_REDACTOR = PiiRedactor()
_CONFIGURED = False


def set_logging_redactor(redactor: PiiRedactor) -> None:
    """Attach an active PiiRedactor (e.g., Cloud DLP enabled) to the log pipeline."""
    global _SHARED_REDACTOR
    _SHARED_REDACTOR = redactor


def _get_active_trace_fields() -> dict[str, str]:
    """Read active OpenTelemetry trace/span IDs for Cloud Logging correlation."""
    try:
        from opentelemetry import trace  # type: ignore[import-untyped]

        span = trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        if ctx is not None and ctx.is_valid:
            trace_id = f"{ctx.trace_id:032x}"
            span_id = f"{ctx.span_id:016x}"
            project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
            fields = {"trace_id": trace_id, "span_id": span_id}
            if project_id and project_id != "your-gcp-project-id":
                fields["logging.googleapis.com/trace"] = (
                    f"projects/{project_id}/traces/{trace_id}"
                )
                fields["logging.googleapis.com/spanId"] = span_id
            return fields
    except Exception:
        pass
    return {}


def _scrub_event_dict(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor that redacts PII and attaches trace metadata."""
    scrubbed: dict[str, Any] = dict(_SHARED_REDACTOR.redact_value(dict(event_dict)))
    scrubbed.update(_get_active_trace_fields())
    if "level" in scrubbed and "severity" not in scrubbed:
        scrubbed["severity"] = str(scrubbed["level"]).upper()
    return scrubbed


class _JsonLogFormatter(logging.Formatter):
    """Stdlib JSON formatter matching Google Cloud Logging structured schema."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "event": _SHARED_REDACTOR.redact_text(record.getMessage()),
        }
        extra_fields = getattr(record, "structured_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(_SHARED_REDACTOR.redact_value(extra_fields))
        payload.update(_get_active_trace_fields())
        return json.dumps(payload, default=str, sort_keys=True)


class StructuredLoggerAdapter:
    """Consistent structured logging interface supporting structlog or stdlib JSON."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._stdlib_logger = logging.getLogger(name)
        self._struct_logger = structlog.get_logger(name) if structlog is not None else None

    def _emit(self, level: str, event: str, **kwargs: Any) -> None:
        if self._struct_logger is not None:
            getattr(self._struct_logger, level)(event, **kwargs)
            return
        log_fn = getattr(self._stdlib_logger, level)
        log_fn(event, extra={"structured_fields": kwargs})

    def debug(self, event: str, **kwargs: Any) -> None:
        self._emit("debug", event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        self._emit("info", event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._emit("warning", event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._emit("error", event, **kwargs)


def configure_logging(level: str = "INFO", redactor: PiiRedactor | None = None) -> None:
    """Configure process-wide structured JSON logging (idempotent)."""
    global _CONFIGURED
    if redactor is not None:
        set_logging_redactor(redactor)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric_level)

    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonLogFormatter())
        root.handlers = [handler]

        if structlog is not None:
            structlog.configure(
                processors=[
                    structlog.contextvars.merge_contextvars,
                    structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="iso", utc=True),
                    _scrub_event_dict,
                    structlog.processors.StackInfoRenderer(),
                    structlog.processors.format_exc_info,
                    structlog.processors.JSONRenderer(sort_keys=True),
                ],
                wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
                logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
                cache_logger_on_first_use=True,
            )
        _CONFIGURED = True


def get_logger(name: str) -> StructuredLoggerAdapter:
    """Return a structured JSON logger bound to `name`."""
    if not _CONFIGURED:
        configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    return StructuredLoggerAdapter(name)
