"""Framework observability module - protocols and utilities for observability.

This module provides protocols for observability that applications can implement.
Unlike the previous implementation, this does not include app-specific database
models or direct provider logging - those belong in the application layer.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from stageflow.observability.tracing import (
    OTEL_AVAILABLE,
    NoOpSpan,
    StageflowTracer,
    TraceContext,
    clear_correlation_id,
    ensure_correlation_id,
    get_correlation_id,
    get_span_id,
    get_trace_context_dict,
    get_trace_id,
    set_correlation_id,
)
from stageflow.observability.wide_events import (
    WideEventEmitter,
    emit_pipeline_wide_event,
    emit_stage_wide_event,
)


class PipelineRunLogger(Protocol):
    """Protocol for logging pipeline runs.

    Applications can implement this to log pipeline execution events
    to their specific observability backend (Datadog, CloudWatch, etc.).
    """

    async def log_run_started(
        self,
        *,
        pipeline_run_id: UUID,
        pipeline_name: str,
        topology: str | None,
        execution_mode: str | None,
        user_id: UUID | None,
        **kwargs: Any,
    ) -> None: ...

    async def log_run_completed(
        self,
        *,
        pipeline_run_id: UUID,
        pipeline_name: str,
        duration_ms: int,
        status: str,
        stage_results: dict[str, Any],
        **kwargs: Any,
    ) -> None: ...

    async def log_run_failed(
        self,
        *,
        pipeline_run_id: UUID,
        pipeline_name: str,
        error: str,
        stage: str | None,
        **kwargs: Any,
    ) -> None: ...


class ProviderCallLogger(Protocol):
    """Protocol for logging external provider API calls.

    Use this to log LLM, STT, TTS, and other external provider calls
    for cost tracking, debugging, and eval tooling.
    """

    async def log_call_start(
        self,
        *,
        operation: str,
        provider: str,
        model_id: str | None,
        **_context: Any,
    ) -> UUID: ...

    async def log_call_end(
        self,
        call_id: UUID,
        *,
        success: bool,
        latency_ms: int,
        error: str | None = None,
        **metrics: Any,
    ) -> None: ...


class CircuitBreaker(Protocol):
    """Protocol for circuit breaker pattern.

    Implement this to prevent cascading failures when
    external services are unavailable.
    """

    async def is_open(self, *, operation: str, provider: str) -> bool: ...

    async def record_success(self, *, operation: str, provider: str) -> None: ...

    async def record_failure(
        self, *, operation: str, provider: str, reason: str
    ) -> None: ...


class CircuitBreakerOpenError(Exception):
    """Raised when a circuit breaker is open."""

    def __init__(self, operation: str, provider: str) -> None:
        super().__init__(f"Circuit breaker open for {operation}/{provider}")
        self.operation = operation
        self.provider = provider


# Utility functions for error handling

def summarize_pipeline_error(exc: Exception) -> dict[str, Any]:
    """Summarize a pipeline error for logging.

    Args:
        exc: The exception to summarize

    Returns:
        Dict with 'code', 'type', 'message', 'retryable' keys
    """
    code = "UNKNOWN"
    stage: str | None = None
    retryable = False

    exc_type = type(exc).__name__
    message = str(exc)

    if isinstance(exc, TimeoutError):
        code = "TIMEOUT"
        retryable = True
    elif "circuit breaker" in message.lower():
        code = "CIRCUIT_OPEN"
        retryable = True

    error_summary: dict[str, Any] = {
        "code": code,
        "type": exc_type,
        "message": message[:500],
        "retryable": retryable,
    }
    if stage is not None:
        error_summary["stage"] = stage
    return error_summary


def error_summary_to_string(error_summary: dict[str, Any]) -> str:
    """Convert error summary dict to string."""
    code = error_summary.get("code") or "UNKNOWN"
    msg = error_summary.get("message") or ""
    return f"{code}: {msg}".strip()


def error_summary_to_stages_patch(error_summary: dict[str, Any]) -> dict[str, Any]:
    """Convert error summary to stages patch format."""
    return {"failure": {"error": error_summary}}


# No-op implementations for convenience

class NoOpPipelineRunLogger:
    """No-op logger for testing or when logging is not needed."""

    async def log_run_started(self, **kwargs: Any) -> None: ...
    async def log_run_completed(self, **kwargs: Any) -> None: ...
    async def log_run_failed(self, **kwargs: Any) -> None: ...


class NoOpProviderCallLogger:
    """No-op provider call logger."""

    async def log_call_start(self, **_kwargs: Any) -> UUID:
        return UUID("00000000-0000-0000-0000-000000000000")

    async def log_call_end(self, call_id: UUID, **_kwargs: Any) -> None: ...


# Default no-op instances
pipeline_run_logger: PipelineRunLogger = NoOpPipelineRunLogger()
provider_call_logger: ProviderCallLogger = NoOpProviderCallLogger()


def get_circuit_breaker() -> CircuitBreaker:
    """Get the configured circuit breaker.

    Returns a no-op circuit breaker by default.
    """
    class NoOpCircuitBreaker:
        async def is_open(self, **_kwargs: Any) -> bool:
            return False

        async def record_success(self, **_kwargs: Any) -> None: ...
        async def record_failure(self, **_kwargs: Any) -> None: ...

    return NoOpCircuitBreaker()


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "NoOpPipelineRunLogger",
    "NoOpProviderCallLogger",
    "NoOpSpan",
    "OTEL_AVAILABLE",
    "PipelineRunLogger",
    "ProviderCallLogger",
    "StageflowTracer",
    "TraceContext",
    "WideEventEmitter",
    "clear_correlation_id",
    "emit_pipeline_wide_event",
    "emit_stage_wide_event",
    "ensure_correlation_id",
    "error_summary_to_stages_patch",
    "error_summary_to_string",
    "get_circuit_breaker",
    "get_correlation_id",
    "get_span_id",
    "get_trace_context_dict",
    "get_trace_id",
    "pipeline_run_logger",
    "provider_call_logger",
    "set_correlation_id",
    "summarize_pipeline_error",
]
