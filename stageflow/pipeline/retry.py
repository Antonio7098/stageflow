"""Retry interceptor with configurable backoff and jitter strategies.

Provides automatic retry handling for transient failures with
exponential backoff, jitter, and configurable retry conditions.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from enum import Enum

from stageflow.pipeline.interceptors import BaseInterceptor, ErrorAction, InterceptorResult
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult

logger = logging.getLogger("stageflow.pipeline.retry")


class BackoffStrategy(Enum):
    """Backoff strategy for retry delays."""

    EXPONENTIAL = "exponential"  # delay = base * 2^attempt
    LINEAR = "linear"  # delay = base * (attempt + 1)
    CONSTANT = "constant"  # delay = base


class JitterStrategy(Enum):
    """Jitter strategy to prevent thundering herd."""

    NONE = "none"  # No jitter
    FULL = "full"  # Random from 0 to delay
    EQUAL = "equal"  # Half fixed, half random
    DECORRELATED = "decorrelated"  # min(max, random(base, prev * 3))


class RetryInterceptor(BaseInterceptor):
    """Interceptor that automatically retries failed stages.

    Supports configurable backoff strategies, jitter, and retry conditions
    to handle transient failures gracefully.

    Example:
        ```python
        from stageflow.pipeline.retry import RetryInterceptor, BackoffStrategy

        retry = RetryInterceptor(
            max_attempts=5,
            base_delay_ms=1000,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_strategy=JitterStrategy.FULL,
        )

        interceptors = get_default_interceptors()
        interceptors.append(retry)
        ```
    """

    name = "retry"
    priority = 15  # Run after circuit breaker, before tracing

    # Default retryable errors
    DEFAULT_RETRYABLE = (
        TimeoutError,
        ConnectionError,
        OSError,
        asyncio.TimeoutError,
    )

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay_ms: int = 1000,
        max_delay_ms: int = 30000,
        backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL,
        jitter_strategy: JitterStrategy = JitterStrategy.FULL,
        retryable_errors: tuple[type[Exception], ...] | None = None,
        retry_on_status: tuple[str, ...] = ("retry",),
    ) -> None:
        """Initialize retry interceptor.

        Args:
            max_attempts: Maximum retry attempts (including initial)
            base_delay_ms: Base delay between retries in milliseconds
            max_delay_ms: Maximum delay cap in milliseconds
            backoff_strategy: How delays grow between attempts
            jitter_strategy: Randomization to prevent thundering herd
            retryable_errors: Exception types that trigger retry
            retry_on_status: StageResult status values that trigger retry
        """
        self.max_attempts = max_attempts
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.backoff_strategy = backoff_strategy
        self.jitter_strategy = jitter_strategy
        self.retryable_errors = retryable_errors or self.DEFAULT_RETRYABLE
        self.retry_on_status = retry_on_status

        # Track delays for decorrelated jitter
        self._previous_delays: dict[str, int] = {}

    async def before(
        self, stage_name: str, ctx: PipelineContext
    ) -> InterceptorResult | None:
        """Initialize retry state before stage execution."""
        # Initialize attempt counter if not present
        retry_key = f"_retry.{stage_name}"
        if retry_key not in ctx.data:
            ctx.data[retry_key] = {
                "attempt": 0,
                "started_at": None,
            }
        return None

    async def after(
        self, stage_name: str, result: StageResult, ctx: PipelineContext
    ) -> None:
        """Clean up retry state after successful completion."""
        retry_key = f"_retry.{stage_name}"

        # Check if result status indicates retry needed
        if result.status in self.retry_on_status:
            await self._handle_retry(stage_name, ctx, result.error or "Retry requested")
            return

        # Clear retry state on success
        if result.status != "failed":
            ctx.data.pop(retry_key, None)
            self._previous_delays.pop(stage_name, None)

    async def on_error(
        self, stage_name: str, error: Exception, ctx: PipelineContext
    ) -> ErrorAction:
        """Handle stage errors with configurable retry logic."""

        # Check if error is retryable
        if not isinstance(error, self.retryable_errors):
            logger.debug(
                f"Error {type(error).__name__} is not retryable",
                extra={
                    "event": "retry_skip_error_type",
                    "stage": stage_name,
                    "error_type": type(error).__name__,
                },
            )
            return ErrorAction.FAIL

        return await self._handle_retry(stage_name, ctx, str(error))

    async def _handle_retry(
        self, stage_name: str, ctx: PipelineContext, error: str
    ) -> ErrorAction:
        """Handle retry logic."""
        retry_key = f"_retry.{stage_name}"
        retry_state = ctx.data.get(retry_key, {"attempt": 0})
        attempt = retry_state.get("attempt", 0)

        # Check if we've exhausted retries
        if attempt >= self.max_attempts - 1:
            logger.warning(
                f"Stage {stage_name} exhausted {self.max_attempts} attempts",
                extra={
                    "event": "retry_exhausted",
                    "stage": stage_name,
                    "attempts": attempt + 1,
                    "error": error,
                },
            )

            # Emit exhausted event
            if hasattr(ctx, "event_sink"):
                with contextlib.suppress(Exception):
                    ctx.event_sink.try_emit(
                        "stage.retry_exhausted",
                        {
                            "stage": stage_name,
                            "attempts": attempt + 1,
                            "error": error,
                        },
                    )

            return ErrorAction.FAIL

        # Calculate delay
        delay_ms = self._calculate_delay(stage_name, attempt)

        logger.info(
            f"Retrying stage {stage_name} in {delay_ms}ms "
            f"(attempt {attempt + 2}/{self.max_attempts})",
            extra={
                "event": "retry_scheduled",
                "stage": stage_name,
                "attempt": attempt + 1,
                "delay_ms": delay_ms,
                "error": error,
            },
        )

        # Emit retry event
        if hasattr(ctx, "event_sink"):
            with contextlib.suppress(Exception):
                ctx.event_sink.try_emit(
                    "stage.retry_scheduled",
                    {
                        "stage": stage_name,
                        "attempt": attempt + 1,
                        "delay_ms": delay_ms,
                        "error": error,
                        "backoff_strategy": self.backoff_strategy.value,
                    },
                )

        # Wait before retry
        await asyncio.sleep(delay_ms / 1000.0)

        # Increment attempt counter
        ctx.data[retry_key] = {
            "attempt": attempt + 1,
            "last_error": error,
        }

        return ErrorAction.RETRY

    def _calculate_delay(self, stage_name: str, attempt: int) -> int:
        """Calculate delay with backoff and jitter."""

        # Base delay from backoff strategy
        if self.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            base_delay = self.base_delay_ms * (2 ** attempt)
        elif self.backoff_strategy == BackoffStrategy.LINEAR:
            base_delay = self.base_delay_ms * (attempt + 1)
        else:  # CONSTANT
            base_delay = self.base_delay_ms

        # Cap at max delay
        base_delay = min(base_delay, self.max_delay_ms)

        # Apply jitter
        if self.jitter_strategy == JitterStrategy.NONE:
            delay = base_delay
        elif self.jitter_strategy == JitterStrategy.FULL:
            delay = random.randint(0, base_delay)
        elif self.jitter_strategy == JitterStrategy.EQUAL:
            half = base_delay // 2
            delay = half + random.randint(0, half)
        else:  # DECORRELATED
            prev = self._previous_delays.get(stage_name, self.base_delay_ms)
            delay = min(self.max_delay_ms, random.randint(self.base_delay_ms, prev * 3))

        # Store for decorrelated jitter
        self._previous_delays[stage_name] = delay

        return delay


class TransientError(Exception):
    """Base class for transient errors that should trigger retry."""
    pass


class RateLimitError(TransientError):
    """Raised when API rate limit is hit."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ServiceUnavailableError(TransientError):
    """Raised when downstream service is temporarily unavailable."""
    pass


__all__ = [
    "BackoffStrategy",
    "JitterStrategy",
    "RateLimitError",
    "RetryInterceptor",
    "ServiceUnavailableError",
    "TransientError",
]
