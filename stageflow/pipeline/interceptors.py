"""Interceptor framework for Stage execution middleware.

Interceptors wrap stage execution to provide cross-cutting concerns:
- Circuit breaking
- Tracing
- Metrics
- Logging
- Authentication/authorization
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult


class ErrorAction(Enum):
    """Action to take when a stage errors."""

    RETRY = auto()  # Retry stage with backoff
    FALLBACK = auto()  # Use fallback result
    FAIL = auto()  # Propagate failure to pipeline


@dataclass(slots=True, kw_only=True)
class InterceptorResult:
    """Result from an interceptor's before() hook.

    If stage_ran is False, the stage is skipped and result is used.
    """

    stage_ran: bool = True
    result: Any = None
    error: str | None = None


class InterceptorError(Exception):
    """Raised when an interceptor fails."""

    def __init__(self, message: str, interceptor_name: str) -> None:
        super().__init__(message)
        self.interceptor_name = interceptor_name


@dataclass(slots=True)
class InterceptorContext:
    """Read-only view of PipelineContext for interceptors."""

    _ctx: PipelineContext
    _interceptor_name: str  # Name of the interceptor that owns this context
    _observations: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """Name of the interceptor that owns this context."""
        return self._interceptor_name

    @property
    def data(self) -> dict[str, Any]:
        """Interceptors get read-only access to stage data."""
        # Return a read-only view (dict copy)
        return self._ctx.data.copy()

    @property
    def pipeline_run_id(self):
        """Access pipeline run ID."""
        return self._ctx.pipeline_run_id

    @property
    def request_id(self):
        """Access request ID."""
        return self._ctx.request_id

    @property
    def session_id(self):
        """Access session ID."""
        return self._ctx.session_id

    @property
    def user_id(self):
        """Access user ID."""
        return self._ctx.user_id

    @property
    def org_id(self):
        """Access org ID."""
        return self._ctx.org_id

    @property
    def topology(self):
        """Access topology."""
        return self._ctx.topology

    @property
    def execution_mode(self):
        """Access execution_mode."""
        return self._ctx.execution_mode

    def add_observation(self, key: str, value: Any) -> None:
        """Interceptors can add observations for other interceptors."""
        namespace = f"_interceptor.{self._interceptor_name}"
        if namespace not in self._ctx.data:
            self._ctx.data[namespace] = {}
        self._ctx.data[namespace][key] = value

    def get_observation(self, key: str) -> Any:
        """Get an observation added by a previous interceptor."""
        namespace = f"_interceptor.{self._interceptor_name}"
        if namespace in self._ctx.data:
            return self._ctx.data[namespace].get(key)
        return None


class BaseInterceptor(ABC):
    """Base class for stage interceptors.

    Interceptors wrap stage execution to add cross-cutting concerns.
    Priority determines execution order: lower = runs first (outer wrapper).
    """

    name: str = "base_interceptor"
    priority: int = 100  # Higher = runs later (inner wrapper)

    @abstractmethod
    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        """Called before stage execution.

        Returns:
            None to continue to next interceptor/stage
            InterceptorResult to short-circuit (stage_ran=False) or modify execution
        """
        return None

    @abstractmethod
    async def after(self, _stage_name: str, _result: StageResult, _ctx: PipelineContext) -> None:
        """Called after stage completes (success or failure)."""
        pass

    async def on_error(
        self, _stage_name: str, _error: Exception, _ctx: PipelineContext
    ) -> ErrorAction:
        """Called when stage throws.

        Returns:
            ErrorAction indicating how to handle the error
        """
        return ErrorAction.FAIL


class ChildTrackerMetricsInterceptor(BaseInterceptor):
    """Interceptor for logging ChildRunTracker metrics."""

    name: str = "child_tracker_metrics"
    priority: int = 45  # Runs after regular metrics but before logging

    async def before(self, _stage_name: str, ctx: PipelineContext) -> None:
        """No-op before method - this interceptor only tracks after execution."""
        pass

    async def after(self, _stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        """Log ChildRunTracker metrics after stage execution."""
        import logging
        
        # Only log metrics for stages that might spawn children
        if hasattr(ctx, 'is_child_run') and ctx.is_child_run:
            logger = logging.getLogger("stageflow.child_tracker_metrics")
            
            try:
                from stageflow.pipeline.subpipeline import get_child_tracker
                tracker = get_child_tracker()
                metrics = await tracker.get_metrics()
                
                logger.info(
                    "ChildRunTracker metrics",
                    extra={
                        "component": "ChildRunTracker",
                        "pipeline_run_id": str(ctx.pipeline_run_id) if ctx.pipeline_run_id else None,
                        "is_child_run": getattr(ctx, 'is_child_run', False),
                        **metrics
                    }
                )
            except Exception as e:
                # Don't let metrics logging break stage execution
                logger.warning(f"Failed to log ChildRunTracker metrics: {e}")


class LoggingInterceptor(BaseInterceptor):
    """Interceptor for structured JSON logging."""

    name: str = "logging"
    priority: int = 50

    async def before(self, stage_name: str, ctx: PipelineContext) -> None:
        import logging

        logger = logging.getLogger("stage_interceptor")
        logger.info(
            f"Stage starting: {stage_name}",
            extra={
                "stage": stage_name,
                "pipeline_run_id": str(ctx.pipeline_run_id) if ctx.pipeline_run_id else None,
                "topology": ctx.topology,
            },
        )

    async def after(self, _stage_name: str, _result: StageResult, _ctx: PipelineContext) -> None:
        import logging

        logger = logging.getLogger("stage_interceptor")
        logger.info(
            f"Stage completed: {_stage_name} - {_result.status}",
            extra={
                "stage": _stage_name,
                "status": _result.status,
                "duration_ms": int((_result.ended_at - _result.started_at).total_seconds() * 1000),
            },
        )


class MetricsInterceptor(BaseInterceptor):
    """Interceptor for recording stage metrics."""

    name: str = "metrics"
    priority: int = 40

    async def before(self, _stage_name: str, ctx: PipelineContext) -> None:
        ctx.data["_metrics.stage_start_time"] = ctx.now()

    async def after(self, _stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        import logging

        logger = logging.getLogger("stage_metrics")
        duration_ms = int((result.ended_at - result.started_at).total_seconds() * 1000)

        # Remove timing key if present
        ctx.data.pop("_metrics.stage_start_time", None)

        logger.info(
            f"Stage metrics: {_stage_name}",
            extra={
                "stage": _stage_name,
                "status": result.status,
                "duration_ms": duration_ms,
                "pipeline_run_id": str(ctx.pipeline_run_id) if ctx.pipeline_run_id else None,
            },
        )


class TracingInterceptor(BaseInterceptor):
    """Interceptor for OpenTelemetry tracing."""

    name: str = "tracing"
    priority: int = 20

    async def before(self, _stage_name: str, ctx: PipelineContext) -> None:
        # Store span context for downstream tracing
        ctx.data["_tracing.span_name"] = _stage_name
        ctx.data["_tracing.span_start"] = ctx.now()

    async def after(self, _stage_name: str, _result: StageResult, ctx: PipelineContext) -> None:
        # Clean up tracing context
        ctx.data.pop("_tracing.span_name", None)
        ctx.data.pop("_tracing.span_start", None)


class CircuitBreakerInterceptor(BaseInterceptor):
    """Interceptor for circuit breaker pattern."""

    name: str = "circuit_breaker"
    priority: int = 10

    def __init__(self) -> None:
        # Simple in-memory circuit breaker state
        self._breaker_states: dict[str, str] = {}  # stage_name -> "closed" | "open" | "half_open"
        self._failure_counts: dict[str, int] = {}
        self._last_failure: dict[str, float] = {}

    async def before(self, stage_name: str, _ctx: PipelineContext) -> InterceptorResult | None:
        state = self._breaker_states.get(stage_name, "closed")

        if state == "open":
            # Check if we should try again (reset timeout)
            import time

            last_failure = self._last_failure.get(stage_name, 0)
            if time.time() - last_failure > 30:  # 30 second reset
                self._breaker_states[stage_name] = "half_open"
            else:
                return InterceptorResult(
                    stage_ran=False,
                    result=None,
                    error=f"Circuit breaker open for {stage_name}",
                )

        return None

    async def after(self, stage_name: str, result: StageResult, _ctx: PipelineContext) -> None:
        if result.status == "failed":
            self._record_failure(stage_name)
        else:
            self._reset_breaker(stage_name)

    async def on_error(
        self, stage_name: str, _error: Exception, _ctx: PipelineContext
    ) -> ErrorAction:
        self._record_failure(stage_name)
        return ErrorAction.FAIL

    def _record_failure(self, stage_name: str) -> None:
        import time

        self._failure_counts[stage_name] = self._failure_counts.get(stage_name, 0) + 1
        self._last_failure[stage_name] = time.time()

        if self._failure_counts[stage_name] >= 5:  # Threshold
            self._breaker_states[stage_name] = "open"

    def _reset_breaker(self, stage_name: str) -> None:
        self._breaker_states[stage_name] = "closed"
        self._failure_counts[stage_name] = 0


class TimeoutInterceptor(BaseInterceptor):
    """Interceptor for stage execution timeout.

    Enforces per-stage timeouts using asyncio.wait_for.
    Timeouts are configurable per-stage via ctx.data['_timeout_ms'].
    """

    name: str = "timeout"
    priority: int = 5  # Runs first (outermost) to catch timeouts early

    # Default timeout in milliseconds (30 seconds)
    DEFAULT_TIMEOUT_MS: int = 30000

    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        # Check for stage-specific timeout or use default
        timeout_ms = ctx.data.get("_timeout_ms", self.DEFAULT_TIMEOUT_MS)

        # Store timeout in context for run_with_interceptors to use
        ctx.data[f"_timeout.{stage_name}"] = timeout_ms

        return None

    async def after(self, stage_name: str, _result: StageResult, ctx: PipelineContext) -> None:
        # Clean up timeout key
        ctx.data.pop(f"_timeout.{stage_name}", None)


def get_default_interceptors(include_auth: bool = False) -> list[BaseInterceptor]:
    """Get the default set of interceptors for pipeline execution.
    
    Args:
        include_auth: Whether to include authentication interceptors
        
    Returns:
        List of interceptors in priority order (low to high)
    """
    interceptors = [
        TimeoutInterceptor(),  # Priority 5 - runs first
        CircuitBreakerInterceptor(),  # Priority 10
        TracingInterceptor(),  # Priority 20
        MetricsInterceptor(),  # Priority 40
        ChildTrackerMetricsInterceptor(),  # Priority 45
        LoggingInterceptor(),  # Priority 50
    ]
    
    if include_auth:
        # Add auth interceptors with appropriate priorities
        from stageflow.auth.interceptors import (
            OrganizationInterceptor,
            RegionInterceptor,
            RateLimitInterceptor,
            PolicyGatewayInterceptor,
        )
        interceptors.extend([
            OrganizationInterceptor(),  # Priority 30
            RegionInterceptor(),  # Priority 35
            RateLimitInterceptor(),  # Priority 37
            PolicyGatewayInterceptor(),  # Priority 39
        ])
    
    return interceptors


async def run_with_interceptors(
    stage_name: str,
    stage_run: Callable,
    ctx: PipelineContext,
    interceptors: list[BaseInterceptor],
) -> StageResult:
    """Execute a stage with interceptor wrapping.

    Args:
        stage_name: Name of the stage being executed
        stage_run: Async callable that runs the stage
        ctx: PipelineContext
        interceptors: List of interceptors to apply (sorted by priority)

    Returns:
        StageResult from the stage execution
    """
    import logging
    from datetime import UTC, datetime

    logger = logging.getLogger("interceptors")
    started_at = datetime.now(UTC)

    # Sort by priority (lower = outer = runs first)
    sorted_interceptors = sorted(interceptors, key=lambda i: i.priority)

    # Create interceptor context for each
    interceptor_contexts = [
        InterceptorContext(ctx, _interceptor_name=i.name) for i in sorted_interceptors
    ]

    # === BEFORE phase ===
    short_circuit_result: InterceptorResult | None = None

    for i, _i_ctx in zip(sorted_interceptors, interceptor_contexts, strict=True):
        try:
            result = await i.before(stage_name, ctx)
            if result is not None and not result.stage_ran:
                short_circuit_result = result
                # Log short-circuit
                logger.info(
                    f"Interceptor {i.name} short-circuited stage {stage_name}",
                    extra={"interceptor": i.name, "stage": stage_name},
                )
                break
        except Exception as e:
            # Isolated interceptor errors don't crash the stage
            logger.error(
                f"Interceptor {i.name} before() failed: {e}",
                extra={"interceptor": i.name, "error": str(e)},
            )

    # === STAGE execution ===
    result: StageResult

    if short_circuit_result is not None:
        # Stage was skipped by interceptor
        ended_at = datetime.now(UTC)
        result = StageResult(
            name=stage_name,
            status="completed",  # Interceptor result is treated as success
            started_at=started_at,
            ended_at=ended_at,
            data=short_circuit_result.result if short_circuit_result.result else {},
            error=short_circuit_result.error,
        )
    else:
        try:
            # Get timeout from context (set by TimeoutInterceptor)
            timeout_ms = ctx.data.get(
                f"_timeout.{stage_name}", TimeoutInterceptor.DEFAULT_TIMEOUT_MS
            )
            timeout_seconds = timeout_ms / 1000.0

            if timeout_seconds > 0:
                # Wrap with timeout using asyncio.wait_for
                import asyncio

                result = await asyncio.wait_for(stage_run(), timeout=timeout_seconds)
            else:
                # No timeout (0 or negative)
                result = await stage_run()
        except TimeoutError:
            ended_at = datetime.now(UTC)
            logger.warning(
                f"Stage {stage_name} timed out after {timeout_ms}ms",
                extra={"stage": stage_name, "timeout_ms": timeout_ms},
            )
            result = StageResult(
                name=stage_name,
                status="failed",
                started_at=started_at,
                ended_at=ended_at,
                error=f"Stage timed out after {timeout_ms}ms",
            )
        except Exception as e:
            # === ERROR phase ===
            error_action = ErrorAction.FAIL
            for i in reversed(sorted_interceptors):
                try:
                    action = await i.on_error(stage_name, e, ctx)
                    if action != ErrorAction.FAIL:
                        error_action = action
                        break
                except Exception as ie:
                    logger.error(
                        f"Interceptor {i.name} on_error() failed: {ie}",
                        extra={"interceptor": i.name, "error": str(ie)},
                    )

            if error_action == ErrorAction.RETRY:
                # Simple retry - could add backoff in future
                try:
                    result = await stage_run()
                except Exception as retry_error:
                    ended_at = datetime.now(UTC)
                    result = StageResult(
                        name=stage_name,
                        status="failed",
                        started_at=started_at,
                        ended_at=ended_at,
                        error=str(retry_error),
                    )
            else:
                ended_at = datetime.now(UTC)
                result = StageResult(
                    name=stage_name,
                    status="failed",
                    started_at=started_at,
                    ended_at=ended_at,
                    error=str(e),
                )

    # === AFTER phase ===
    for i, _i_ctx in zip(
        reversed(sorted_interceptors), reversed(interceptor_contexts), strict=True
    ):
        try:
            await i.after(stage_name, result, ctx)
        except Exception as e:
            # Isolated - don't crash the stage
            logger.error(
                f"Interceptor {i.name} after() failed: {e}",
                extra={"interceptor": i.name, "error": str(e)},
            )

    return result


__all__ = [
    "BaseInterceptor",
    "InterceptorResult",
    "InterceptorContext",
    "InterceptorError",
    "ErrorAction",
    "BaseInterceptor",
    "LoggingInterceptor",
    "MetricsInterceptor",
    "ChildTrackerMetricsInterceptor",
    "TracingInterceptor",
    "CircuitBreakerInterceptor",
    "TimeoutInterceptor",
    "get_default_interceptors",
    "run_with_interceptors",
]
