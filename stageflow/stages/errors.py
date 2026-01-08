"""Error handling utilities for stages and pipelines.

This module provides consistent error handling patterns and logging utilities
for pipeline stages.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stageflow.stages.context import PipelineContext

logger = logging.getLogger("stage_errors")


def log_stage_error(
    stage_name: str,
    error: Exception,
    ctx: PipelineContext | None = None,
    stage_logger: logging.Logger | None = None,
    additional_context: dict[str, Any] | None = None,
) -> None:
    """Log a stage error with full context."""
    stage_logger = stage_logger or logging.getLogger("pipeline_error")
    extra: dict[str, Any] = {
        "service": "pipeline",
        "stage": stage_name,
        "error_type": type(error).__name__,
        "error_message": str(error),
    }
    if ctx:
        extra.update(
            {
                "pipeline_run_id": str(ctx.pipeline_run_id) if ctx.pipeline_run_id else None,
                "request_id": str(ctx.request_id) if ctx.request_id else None,
                "session_id": str(ctx.session_id) if ctx.session_id else None,
                "user_id": str(ctx.user_id) if ctx.user_id else None,
                "org_id": str(ctx.org_id) if ctx.org_id else None,
            }
        )
    if additional_context:
        extra.update(additional_context)
    stage_logger.error("Stage %s failed: %s", stage_name, error, extra=extra, exc_info=True)


def log_debug_failure(
    operation: str, error: Exception, context: dict[str, Any] | None = None
) -> None:
    """Log a debug operation failure."""
    debug_logger = logging.getLogger("debug_operations")
    extra: dict[str, Any] = {
        "service": "debug",
        "operation": operation,
        "error_type": type(error).__name__,
        "error_message": str(error),
    }
    if context:
        extra.update(context)
    debug_logger.error("Debug operation failed: %s", operation, extra=extra, exc_info=True)


def safe_debug_log(operation: str, log_func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Safely execute a logging function with error handling."""
    try:
        log_func(*args, **kwargs)
    except Exception as exc:
        log_debug_failure(operation, exc)


def handle_provider_error(
    provider_name: str,
    operation: str,
    error: Exception,
    ctx: PipelineContext | None = None,
) -> None:
    """Log a provider error with full context."""
    provider_logger = logging.getLogger("provider_error")
    extra: dict[str, Any] = {
        "service": "provider",
        "provider": provider_name,
        "operation": operation,
        "error_type": type(error).__name__,
        "error_message": str(error),
    }
    if ctx:
        extra.update(
            {
                "pipeline_run_id": str(ctx.pipeline_run_id) if ctx.pipeline_run_id else None,
                "request_id": str(ctx.request_id) if ctx.request_id else None,
                "session_id": str(ctx.session_id) if ctx.session_id else None,
            }
        )
    provider_logger.error(
        "Provider %s error during %s: %s",
        provider_name,
        operation,
        error,
        extra=extra,
        exc_info=True,
    )


def handle_async_task_error(
    task_name: str,
    error: Exception,
    context: dict[str, Any] | None = None,
) -> None:
    """Log an async task error."""
    task_logger = logging.getLogger("async_tasks")
    extra: dict[str, Any] = {
        "service": "async_tasks",
        "task_name": task_name,
        "error_type": type(error).__name__,
        "error_message": str(error),
    }
    if context:
        extra.update(context)
    task_logger.error(
        "Background task '%s' failed: %s", task_name, error, extra=extra, exc_info=True
    )


def create_error_context(**kwargs: Any) -> dict[str, Any]:
    """Create an error context with timestamp."""
    record = logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    )
    return {"error_timestamp": record.created, **kwargs}


def with_error_handling(
    stage_name: str,
    error_message: str | None = None,
    record_payload_fn: Callable[[Exception, dict[str, Any]], dict[str, Any]] | None = None,
) -> Callable:
    """Decorator for consistent stage error handling.

    Args:
        stage_name: Name of the stage for error messages and events
        error_message: Custom error message prefix
        record_payload_fn: Optional function to add custom fields to error payload

    Returns:
        Decorated async function with consistent error handling

    Example:
        @with_error_handling(stage_name="my_stage", error_message="My stage failed")
        async def run(self, ctx: PipelineContext) -> StageResult:
            # Stage work here
            return StageResult(...)
    """
    from stageflow.pipeline.dag import StageExecutionError
    from stageflow.stages.context import PipelineContext
    from stageflow.stages.result import StageError, StageResult

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args: Any, **kwargs: Any) -> StageResult:
            # Find the run method and its context
            _self_arg = args[0] if args else None
            ctx: PipelineContext | None = None
            for arg in args:
                if isinstance(arg, PipelineContext):
                    ctx = arg
                    break
            if ctx is None:
                ctx = kwargs.get("ctx")

            started_at = datetime.now(UTC)

            try:
                # Execute the actual stage logic
                result = await func(*args, **kwargs)

                # If result is already a StageResult, return it
                if isinstance(result, StageResult):
                    result.started_at = started_at
                    result.ended_at = datetime.now(UTC)
                    return result

                # If result is a dict, wrap it
                return StageResult(
                    name=stage_name,
                    status="completed",
                    started_at=started_at,
                    ended_at=datetime.now(UTC),
                    data=result if isinstance(result, dict) else {},
                )

            except StageError as e:
                # Semantic errors - record and re-raise
                error_msg = str(e) or error_message or f"{stage_name} error"
                logger.warning(
                    error_msg,
                    extra={"service": "stage", "stage": stage_name, "error": str(e)},
                )

                if ctx:
                    payload: dict[str, Any] = {"error": str(e)}
                    if record_payload_fn:
                        payload.update(record_payload_fn(e, payload))
                    ctx.record_stage_event(
                        stage=stage_name,
                        status="failed",
                        payload=payload,
                    )

                raise

            except Exception as e:
                # Execution errors - record and re-raise
                error_msg = f"{error_message or stage_name} failed: {e}"
                logger.exception(
                    error_msg,
                    extra={"service": "stage", "stage": stage_name, "error": str(e)},
                )

                if ctx:
                    payload: dict[str, Any] = {
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                    if record_payload_fn:
                        payload.update(record_payload_fn(e, payload))
                    ctx.record_stage_event(
                        stage=stage_name,
                        status="failed",
                        payload=payload,
                    )

                # Wrap in StageExecutionError for clarity
                raise StageExecutionError(
                    stage=stage_name,
                    original=e,
                    recoverable=_is_recoverable_error(e),
                ) from e

        return wrapper

    return decorator


def _is_recoverable_error(error: Exception) -> bool:
    """Determine if an error is recoverable (pipeline can continue)."""
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()

    # Network errors are typically recoverable
    recoverable_keywords = [
        "connection",
        "timeout",
        "network",
        "disconnected",
        "server disconnected",
    ]

    recoverable_types = [
        "connectionerror",
        "timeouterror",
        "httperror",
    ]

    return (
        any(keyword in error_str for keyword in recoverable_keywords)
        or error_type in recoverable_types
    )


class StageRunner:
    """Utility class for running stages with consistent error handling.

    Usage:
        runner = StageRunner(stage_name="my_stage", ctx=ctx)
        result = await runner.run(
            run_fn=lambda: self._do_work(),
            error_message="My stage failed",
        )
    """

    def __init__(
        self,
        stage_name: str,
        ctx: PipelineContext,
        error_message: str | None = None,
    ) -> None:
        self.stage_name = stage_name
        self.ctx = ctx
        self.error_message = error_message or stage_name

    async def run(
        self,
        run_fn: Callable[[], Any],
        *,
        on_success: Callable[[Any], dict[str, Any]] | None = None,
        on_error: Callable[[Exception], dict[str, Any]] | None = None,
    ):
        """Run a stage function with consistent error handling.

        Args:
            run_fn: Async function to execute
            on_success: Optional function to transform successful result to data dict
            on_error: Optional function to add fields to error payload

        Returns:
            StageResult with status and data
        """
        from stageflow.pipeline.dag import StageExecutionError
        from stageflow.stages.result import StageResult

        started_at = datetime.now(UTC)

        try:
            result = run_fn()

            # Handle async generators and awaitables
            if hasattr(result, "__await__"):
                result = await result

            data = (on_success and on_success(result)) or (
                result if isinstance(result, dict) else {}
            )
            status = "completed"

            # Record completed event
            self.ctx.record_stage_event(
                stage=self.stage_name,
                status=status,
                payload={"data_keys": list(data.keys())} if data else None,
            )

            return StageResult(
                name=self.stage_name,
                status=status,
                started_at=started_at,
                ended_at=datetime.now(UTC),
                data=data,
            )

        except Exception as e:
            logger.exception(
                f"{self.error_message}: {e}",
                extra={"service": "stage", "stage": self.stage_name, "error": str(e)},
            )

            error_payload: dict[str, Any] = {
                "error": str(e),
                "error_type": type(e).__name__,
            }
            if on_error:
                error_payload.update(on_error(e))

            self.ctx.record_stage_event(
                stage=self.stage_name,
                status="failed",
                payload=error_payload,
            )

            raise StageExecutionError(
                stage=self.stage_name,
                original=e,
                recoverable=_is_recoverable_error(e),
            ) from e


__all__ = [
    "log_stage_error",
    "log_debug_failure",
    "safe_debug_log",
    "handle_provider_error",
    "handle_async_task_error",
    "create_error_context",
    "with_error_handling",
    "StageRunner",
    "_is_recoverable_error",
]
