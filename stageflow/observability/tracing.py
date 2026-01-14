"""OpenTelemetry integration for stageflow.

This module provides utilities for distributed tracing and correlation ID
propagation across async boundaries. It integrates with OpenTelemetry
for standardized observability.

Features:
- Correlation ID propagation via contextvars
- Span creation and management
- Trace context propagation across async boundaries
- Integration with stageflow events

Note: OpenTelemetry SDK is optional. If not installed, this module
provides no-op implementations that maintain correlation IDs without
actual tracing.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import UUID, uuid4

logger = logging.getLogger("stageflow.observability.tracing")

T = TypeVar("T")

# Context variables for correlation IDs
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_span_id: ContextVar[str | None] = ContextVar("span_id", default=None)
_parent_span_id: ContextVar[str | None] = ContextVar("parent_span_id", default=None)
_correlation_id: ContextVar[UUID | None] = ContextVar("correlation_id", default=None)

# Try to import OpenTelemetry, fall back to no-op if not available
try:
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None  # type: ignore
    Context = None  # type: ignore
    SpanKind = None  # type: ignore
    Status = None  # type: ignore
    StatusCode = None  # type: ignore
    Tracer = None  # type: ignore
    TraceContextTextMapPropagator = None  # type: ignore


@dataclass
class TraceContext:
    """Container for trace context that can be propagated across boundaries.

    This class captures all correlation IDs and trace information needed
    to maintain observability across async boundaries, service calls,
    and message queues.

    Example:
        # Capture current context
        ctx = TraceContext.capture()

        # Pass to another task/service
        async def worker(trace_ctx: TraceContext):
            with trace_ctx.activate():
                # All operations here have the same trace context
                await do_work()
    """

    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    correlation_id: UUID | None = None
    pipeline_run_id: UUID | None = None
    request_id: UUID | None = None
    org_id: UUID | None = None
    baggage: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def capture(cls) -> TraceContext:
        """Capture the current trace context from contextvars.

        Returns:
            TraceContext with current values.
        """
        ctx = cls(
            trace_id=_trace_id.get(),
            span_id=_span_id.get(),
            parent_span_id=_parent_span_id.get(),
            correlation_id=_correlation_id.get(),
        )

        # If OpenTelemetry is available, also capture from OTEL context
        if OTEL_AVAILABLE and trace is not None:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                span_ctx = current_span.get_span_context()
                if span_ctx.is_valid:
                    ctx = TraceContext(
                        trace_id=format(span_ctx.trace_id, "032x"),
                        span_id=format(span_ctx.span_id, "016x"),
                        parent_span_id=ctx.parent_span_id,
                        correlation_id=ctx.correlation_id,
                        pipeline_run_id=ctx.pipeline_run_id,
                        request_id=ctx.request_id,
                        org_id=ctx.org_id,
                        baggage=ctx.baggage,
                    )

        return ctx

    @contextmanager
    def activate(self):
        """Activate this trace context in the current context.

        Yields:
            None - context is active within the with block.
        """
        tokens = []

        if self.trace_id:
            tokens.append((_trace_id, _trace_id.set(self.trace_id)))
        if self.span_id:
            tokens.append((_span_id, _span_id.set(self.span_id)))
        if self.parent_span_id:
            tokens.append((_parent_span_id, _parent_span_id.set(self.parent_span_id)))
        if self.correlation_id:
            tokens.append((_correlation_id, _correlation_id.set(self.correlation_id)))

        try:
            yield
        finally:
            for var, token in tokens:
                var.reset(token)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization/logging."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "request_id": str(self.request_id) if self.request_id else None,
            "org_id": str(self.org_id) if self.org_id else None,
            "baggage": self.baggage,
            "created_at": self.created_at.isoformat(),
        }

    def to_headers(self) -> dict[str, str]:
        """Convert to HTTP headers for propagation.

        Returns:
            Dictionary of headers suitable for HTTP requests.
        """
        headers: dict[str, str] = {}

        if self.trace_id:
            # W3C Trace Context format
            traceparent = f"00-{self.trace_id}-{self.span_id or '0' * 16}-01"
            headers["traceparent"] = traceparent

        if self.correlation_id:
            headers["x-correlation-id"] = str(self.correlation_id)
        if self.pipeline_run_id:
            headers["x-pipeline-run-id"] = str(self.pipeline_run_id)
        if self.request_id:
            headers["x-request-id"] = str(self.request_id)
        if self.org_id:
            headers["x-org-id"] = str(self.org_id)

        for key, value in self.baggage.items():
            headers[f"x-baggage-{key}"] = value

        return headers

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> TraceContext:
        """Create TraceContext from HTTP headers.

        Args:
            headers: Dictionary of HTTP headers.

        Returns:
            TraceContext populated from headers.
        """
        ctx = cls()

        # Parse W3C Trace Context
        traceparent = headers.get("traceparent")
        if traceparent:
            parts = traceparent.split("-")
            if len(parts) >= 3:
                ctx = TraceContext(
                    trace_id=parts[1] if len(parts[1]) == 32 else None,
                    span_id=parts[2] if len(parts[2]) == 16 else None,
                )

        # Parse custom headers
        if headers.get("x-correlation-id"):
            with suppress(ValueError):
                ctx = TraceContext(
                    trace_id=ctx.trace_id,
                    span_id=ctx.span_id,
                    correlation_id=UUID(headers["x-correlation-id"]),
                )

        if headers.get("x-pipeline-run-id"):
            with suppress(ValueError):
                ctx = TraceContext(
                    trace_id=ctx.trace_id,
                    span_id=ctx.span_id,
                    correlation_id=ctx.correlation_id,
                    pipeline_run_id=UUID(headers["x-pipeline-run-id"]),
                )

        if headers.get("x-request-id"):
            with suppress(ValueError):
                ctx = TraceContext(
                    trace_id=ctx.trace_id,
                    span_id=ctx.span_id,
                    correlation_id=ctx.correlation_id,
                    pipeline_run_id=ctx.pipeline_run_id,
                    request_id=UUID(headers["x-request-id"]),
                )

        if headers.get("x-org-id"):
            with suppress(ValueError):
                ctx = TraceContext(
                    trace_id=ctx.trace_id,
                    span_id=ctx.span_id,
                    correlation_id=ctx.correlation_id,
                    pipeline_run_id=ctx.pipeline_run_id,
                    request_id=ctx.request_id,
                    org_id=UUID(headers["x-org-id"]),
                )

        # Parse baggage
        baggage = {}
        for key, value in headers.items():
            if key.startswith("x-baggage-"):
                baggage_key = key[len("x-baggage-") :]
                baggage[baggage_key] = value

        if baggage:
            ctx = TraceContext(
                trace_id=ctx.trace_id,
                span_id=ctx.span_id,
                correlation_id=ctx.correlation_id,
                pipeline_run_id=ctx.pipeline_run_id,
                request_id=ctx.request_id,
                org_id=ctx.org_id,
                baggage=baggage,
            )

        return ctx


class StageflowTracer:
    """Tracer wrapper that works with or without OpenTelemetry.

    Provides a consistent API for creating spans and propagating
    trace context, falling back to no-op implementations when
    OpenTelemetry is not available.

    Example:
        tracer = StageflowTracer("my_service")

        with tracer.start_span("process_request") as span:
            span.set_attribute("user_id", str(user_id))
            result = await process()
            span.set_attribute("result_size", len(result))
    """

    def __init__(self, name: str = "stageflow") -> None:
        self._name = name
        self._tracer: Tracer | None = None

        if OTEL_AVAILABLE and trace is not None:
            self._tracer = trace.get_tracer(name)

    @property
    def is_enabled(self) -> bool:
        """Check if actual tracing is enabled."""
        return self._tracer is not None

    @contextmanager
    def start_span(
        self,
        name: str,
        *,
        kind: Any = None,
        attributes: dict[str, Any] | None = None,
    ):
        """Start a new span.

        Args:
            name: Span name.
            kind: Span kind (server, client, etc.).
            attributes: Initial span attributes.

        Yields:
            Span object (real or no-op).
        """
        if self._tracer is not None and OTEL_AVAILABLE:
            span_kind = kind if kind is not None else SpanKind.INTERNAL
            with self._tracer.start_as_current_span(
                name,
                kind=span_kind,
                attributes=attributes,
            ) as span:
                # Update contextvars
                span_ctx = span.get_span_context()
                if span_ctx.is_valid:
                    old_trace = _trace_id.set(format(span_ctx.trace_id, "032x"))
                    old_span = _span_id.set(format(span_ctx.span_id, "016x"))
                    try:
                        yield span
                    finally:
                        _trace_id.reset(old_trace)
                        _span_id.reset(old_span)
                else:
                    yield span
        else:
            # No-op span
            yield NoOpSpan(name, attributes=attributes)

    def inject_context(self, carrier: dict[str, str]) -> None:
        """Inject current trace context into a carrier (e.g., headers).

        Args:
            carrier: Dictionary to inject context into.
        """
        if OTEL_AVAILABLE and TraceContextTextMapPropagator is not None:
            propagator = TraceContextTextMapPropagator()
            propagator.inject(carrier)

        # Also inject our custom context
        ctx = TraceContext.capture()
        carrier.update(ctx.to_headers())

    def extract_context(self, carrier: dict[str, str]) -> TraceContext:
        """Extract trace context from a carrier (e.g., headers).

        Args:
            carrier: Dictionary containing context.

        Returns:
            Extracted TraceContext.
        """
        return TraceContext.from_headers(carrier)


class NoOpSpan:
    """No-op span implementation when OpenTelemetry is not available."""

    def __init__(self, name: str, *, attributes: dict[str, Any] | None = None) -> None:
        self._name = name
        self._attributes = attributes or {}
        self._events: list[tuple[str, dict[str, Any]]] = []

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute."""
        self._attributes[key] = value

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add an event to the span."""
        self._events.append((name, attributes or {}))

    def set_status(self, status: Any, description: str | None = None) -> None:
        """Set span status."""
        self._attributes["_status"] = str(status)
        if description:
            self._attributes["_status_description"] = description

    def record_exception(self, exception: Exception) -> None:
        """Record an exception on the span."""
        self.add_event(
            "exception",
            {
                "exception.type": type(exception).__name__,
                "exception.message": str(exception),
            },
        )

    def is_recording(self) -> bool:
        """Check if span is recording."""
        return False

    def get_span_context(self) -> Any:
        """Get span context."""
        return None


# Convenience functions for working with correlation IDs

def set_correlation_id(correlation_id: UUID) -> None:
    """Set the current correlation ID."""
    _correlation_id.set(correlation_id)


def get_correlation_id() -> UUID | None:
    """Get the current correlation ID."""
    return _correlation_id.get()


def ensure_correlation_id() -> UUID:
    """Get or create a correlation ID.

    Returns:
        Existing correlation ID or a new one if not set.
    """
    cid = _correlation_id.get()
    if cid is None:
        cid = uuid4()
        _correlation_id.set(cid)
    return cid


def clear_correlation_id() -> None:
    """Clear the current correlation ID."""
    _correlation_id.set(None)


def get_trace_id() -> str | None:
    """Get the current trace ID."""
    return _trace_id.get()


def get_span_id() -> str | None:
    """Get the current span ID."""
    return _span_id.get()


def get_trace_context_dict() -> dict[str, Any]:
    """Get all trace context as a dictionary.

    Useful for adding to log records or event data.
    """
    return {
        "trace_id": _trace_id.get(),
        "span_id": _span_id.get(),
        "parent_span_id": _parent_span_id.get(),
        "correlation_id": str(_correlation_id.get()) if _correlation_id.get() else None,
    }


__all__ = [
    "OTEL_AVAILABLE",
    "NoOpSpan",
    "StageflowTracer",
    "TraceContext",
    "clear_correlation_id",
    "ensure_correlation_id",
    "get_correlation_id",
    "get_span_id",
    "get_trace_context_dict",
    "get_trace_id",
    "set_correlation_id",
]
