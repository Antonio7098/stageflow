"""Structured cancellation support for pipeline execution.

This module provides utilities for proper resource cleanup during
pipeline cancellation using Python 3.11+ TaskGroup semantics.

Features:
- Automatic cleanup of resources on cancellation
- Context manager for cleanup registration
- Cleanup callbacks with timeout support
- Structured concurrency patterns
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar

logger = logging.getLogger("stageflow.cancellation")

T = TypeVar("T")
CleanupCallback = Callable[[], Awaitable[None]]


@dataclass
class CleanupRegistry:
    """Registry for cleanup callbacks that run on cancellation.

    Cleanup callbacks are executed in LIFO order (last registered, first executed)
    to properly unwind resource acquisition.

    Example:
        registry = CleanupRegistry()

        async def cleanup_connection():
            await connection.close()

        registry.register(cleanup_connection)

        # On cancellation:
        await registry.run_all(timeout=5.0)
    """

    _callbacks: list[CleanupCallback] = field(default_factory=list)
    _completed: list[str] = field(default_factory=list)
    _failed: list[tuple[str, Exception]] = field(default_factory=list)

    def register(self, callback: CleanupCallback, *, name: str | None = None) -> None:
        """Register a cleanup callback.

        Args:
            callback: Async function to call during cleanup.
            name: Optional name for logging/debugging.
        """
        if name:
            callback.__cleanup_name__ = name  # type: ignore[attr-defined]
        self._callbacks.append(callback)

    def unregister(self, callback: CleanupCallback) -> bool:
        """Unregister a cleanup callback.

        Args:
            callback: The callback to remove.

        Returns:
            True if callback was found and removed, False otherwise.
        """
        try:
            self._callbacks.remove(callback)
            return True
        except ValueError:
            return False

    async def run_all(self, *, timeout: float = 10.0) -> tuple[list[str], list[tuple[str, Exception]]]:
        """Run all cleanup callbacks in LIFO order.

        Args:
            timeout: Maximum time to wait for all cleanups.

        Returns:
            Tuple of (completed callback names, failed callback names with exceptions).
        """
        self._completed = []
        self._failed = []

        if not self._callbacks:
            return self._completed, self._failed

        # Calculate per-callback timeout
        per_callback_timeout = max(timeout / len(self._callbacks), 0.01)

        # Execute in reverse order (LIFO)
        for callback in reversed(self._callbacks.copy()):
            name = getattr(callback, "__cleanup_name__", callback.__name__)
            try:
                await asyncio.wait_for(callback(), timeout=per_callback_timeout)
                self._completed.append(name)
                logger.debug(f"Cleanup completed: {name}")
            except TimeoutError:
                self._failed.append((name, TimeoutError(f"Cleanup timed out: {name}")))
                logger.warning(f"Cleanup timed out: {name}")
            except asyncio.CancelledError:
                self._failed.append((name, asyncio.CancelledError(f"Cleanup cancelled: {name}")))
                logger.warning(f"Cleanup cancelled: {name}")
            except Exception as e:
                self._failed.append((name, e))
                logger.error(f"Cleanup failed: {name}", exc_info=True)

        self._callbacks.clear()
        return self._completed, self._failed

    @property
    def pending_count(self) -> int:
        """Number of pending cleanup callbacks."""
        return len(self._callbacks)


@dataclass
class CancellationToken:
    """Token for cooperative cancellation.

    Stages can check this token to determine if cancellation has been
    requested and perform graceful shutdown.

    Example:
        async def my_stage(ctx: StageContext, cancel_token: CancellationToken):
            while not cancel_token.is_cancelled:
                # Do work
                await process_chunk()

            # Cleanup before returning
            await cleanup()
    """

    _cancelled: bool = False
    _reason: str | None = None
    _callbacks: list[Callable[[], None]] = field(default_factory=list)

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self._cancelled

    @property
    def reason(self) -> str | None:
        """Get the cancellation reason if cancelled."""
        return self._reason

    def cancel(self, reason: str = "Cancellation requested") -> None:
        """Request cancellation.

        Args:
            reason: Human-readable reason for cancellation.
        """
        if self._cancelled:
            return
        self._cancelled = True
        self._reason = reason
        for callback in self._callbacks:
            try:
                callback()
            except Exception:
                logger.exception("Error in cancellation callback")

    def on_cancel(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when cancelled.

        Args:
            callback: Synchronous function to call on cancellation.
        """
        if self._cancelled:
            callback()
        else:
            self._callbacks.append(callback)


class StructuredTaskGroup:
    """TaskGroup wrapper with cleanup support.

    Provides structured concurrency with automatic cleanup on
    cancellation or error.

    Example:
        async with StructuredTaskGroup() as tg:
            tg.create_task(stage_a())
            tg.create_task(stage_b())
            # If any task fails, all others are cancelled
            # and cleanup callbacks are run
    """

    def __init__(self, *, cleanup_timeout: float = 10.0) -> None:
        self._cleanup_timeout = cleanup_timeout
        self._cleanup_registry = CleanupRegistry()
        self._tasks: list[asyncio.Task[Any]] = []
        self._cancel_token = CancellationToken()

    @property
    def cleanup_registry(self) -> CleanupRegistry:
        """Get the cleanup registry for this task group."""
        return self._cleanup_registry

    @property
    def cancel_token(self) -> CancellationToken:
        """Get the cancellation token for this task group."""
        return self._cancel_token

    def create_task(self, coro: Awaitable[T], *, name: str | None = None) -> asyncio.Task[T]:
        """Create a task within this group.

        Args:
            coro: Coroutine to run.
            name: Optional task name.

        Returns:
            The created task.
        """
        task = asyncio.create_task(coro, name=name)
        self._tasks.append(task)
        return task

    async def _cancel_all(self) -> None:
        """Cancel all running tasks."""
        self._cancel_token.cancel("Task group shutting down")
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def __aenter__(self) -> StructuredTaskGroup:
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any) -> bool:
        """Exit the task group, running cleanup on error or cancellation."""
        first_exception: Exception | None = exc_val

        try:
            if exc_type is not None:
                # Error occurred in the with block, cancel all tasks
                self._cancel_token.cancel("Exception in task group")
                await self._cancel_all()
            else:
                # Wait for all tasks to complete normally
                if self._tasks:
                    results = await asyncio.gather(*self._tasks, return_exceptions=True)
                    # Check for exceptions in results
                    for result in results:
                        if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                            if first_exception is None:
                                first_exception = result
                            # Cancel remaining tasks on first error
                            self._cancel_token.cancel("Task failed")
                            await self._cancel_all()
                            break
        finally:
            # Always run cleanup
            if self._cleanup_registry.pending_count > 0:
                completed, failed = await self._cleanup_registry.run_all(
                    timeout=self._cleanup_timeout
                )
                if failed:
                    logger.warning(
                        f"Some cleanup callbacks failed: {[name for name, _ in failed]}"
                    )

        # Re-raise the first exception from tasks if there was one
        if first_exception is not None and exc_val is None:
            raise first_exception

        return False  # Don't suppress exceptions


@asynccontextmanager
async def cleanup_on_cancel(cleanup: CleanupCallback, *, name: str | None = None):
    """Context manager that ensures cleanup runs on cancellation.

    Example:
        async with cleanup_on_cancel(close_connection, name="db_connection"):
            await do_work()
        # close_connection() is called if cancelled or on normal exit
    """
    try:
        yield
    finally:
        try:
            await cleanup()
            if name:
                logger.debug(f"Cleanup completed: {name}")
        except Exception:
            if name:
                logger.exception(f"Cleanup failed: {name}")
            raise


async def run_with_cleanup(
    coro: Awaitable[T],
    cleanup: CleanupCallback,
    *,
    cleanup_timeout: float = 5.0,
) -> T:
    """Run a coroutine with guaranteed cleanup.

    Args:
        coro: The coroutine to run.
        cleanup: Cleanup function to call after coro completes or is cancelled.
        cleanup_timeout: Maximum time to wait for cleanup.

    Returns:
        The result of the coroutine.
    """
    try:
        return await coro
    finally:
        try:
            await asyncio.wait_for(cleanup(), timeout=cleanup_timeout)
        except TimeoutError:
            logger.warning("Cleanup timed out")
        except Exception:
            logger.exception("Cleanup failed")


__all__ = [
    "CleanupRegistry",
    "CancellationToken",
    "StructuredTaskGroup",
    "cleanup_on_cancel",
    "run_with_cleanup",
]
