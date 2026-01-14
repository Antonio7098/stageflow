"""Event sink implementations for stageflow.

This module provides the EventSink protocol and default implementations:
- NoOpEventSink: Discards all events (default)
- LoggingEventSink: Logs events to Python logging
- BackpressureAwareEventSink: Bounded queue with backpressure handling and metrics
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("stageflow.events")


@runtime_checkable
class EventSink(Protocol):
    """Protocol for event persistence/emission."""

    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        """Emit an event asynchronously."""
        ...

    def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        """Emit an event without blocking (fire-and-forget)."""
        ...


class NoOpEventSink:
    """Event sink that discards all events."""

    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        _ = type, data
        return None

    def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        _ = type, data
        return None


class LoggingEventSink:
    """Event sink that logs events to Python logging."""

    def __init__(self, *, level: int = logging.INFO) -> None:
        self._level = level
        self._logger = logging.getLogger("stageflow.events")

    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        self._logger.log(
            self._level,
            "Event: %s",
            type,
            extra={"event_type": type, "event_data": data},
        )

    def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        self._logger.log(
            self._level,
            "Event: %s",
            type,
            extra={"event_type": type, "event_data": data},
        )


@dataclass
class BackpressureMetrics:
    """Metrics for backpressure-aware event sink."""

    emitted: int = 0
    dropped: int = 0
    queue_full_count: int = 0
    last_emit_time: float = 0.0
    last_drop_time: float = 0.0

    def record_emit(self) -> None:
        self.emitted += 1
        self.last_emit_time = time.monotonic()

    def record_drop(self) -> None:
        self.dropped += 1
        self.queue_full_count += 1
        self.last_drop_time = time.monotonic()

    @property
    def drop_rate(self) -> float:
        """Calculate drop rate as percentage."""
        total = self.emitted + self.dropped
        if total == 0:
            return 0.0
        return (self.dropped / total) * 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "emitted": self.emitted,
            "dropped": self.dropped,
            "queue_full_count": self.queue_full_count,
            "drop_rate_percent": round(self.drop_rate, 2),
            "last_emit_time": self.last_emit_time,
            "last_drop_time": self.last_drop_time,
        }


class BackpressureAwareEventSink:
    """Event sink with bounded queue and backpressure handling.

    This sink buffers events in a bounded asyncio.Queue and processes them
    asynchronously. When the queue is full, events are dropped and metrics
    are recorded.

    Features:
    - Bounded queue prevents memory exhaustion under load
    - Metrics track emitted/dropped events for observability
    - Background worker processes events asynchronously
    - Graceful shutdown with drain support

    Example:
        sink = BackpressureAwareEventSink(
            downstream=DatabaseEventSink(),
            max_queue_size=1000,
        )
        await sink.start()

        # Use the sink
        sink.try_emit(type="event.type", data={"key": "value"})

        # Shutdown gracefully
        await sink.stop()
    """

    def __init__(
        self,
        downstream: EventSink | None = None,
        *,
        max_queue_size: int = 1000,
        on_drop: Callable[[str, dict[str, Any] | None], None] | None = None,
    ) -> None:
        self._downstream = downstream or LoggingEventSink()
        self._queue: asyncio.Queue[tuple[str, dict[str, Any] | None]] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self._max_queue_size = max_queue_size
        self._metrics = BackpressureMetrics()
        self._on_drop = on_drop
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False
        self._logger = logging.getLogger("stageflow.events.backpressure")

    @property
    def metrics(self) -> BackpressureMetrics:
        """Get current metrics."""
        return self._metrics

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        """Check if the worker is running."""
        return self._running

    async def start(self) -> None:
        """Start the background worker."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        self._logger.info(
            "BackpressureAwareEventSink started",
            extra={"max_queue_size": self._max_queue_size},
        )

    async def stop(self, *, drain: bool = True, timeout: float = 5.0) -> None:
        """Stop the background worker.

        Args:
            drain: If True, process remaining events before stopping.
            timeout: Maximum time to wait for drain.
        """
        if not self._running:
            return

        self._running = False

        if drain and not self._queue.empty():
            try:
                await asyncio.wait_for(self._drain(), timeout=timeout)
            except TimeoutError:
                self._logger.warning(
                    "Drain timeout, some events may be lost",
                    extra={"remaining": self._queue.qsize()},
                )

        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None

        self._logger.info(
            "BackpressureAwareEventSink stopped",
            extra={"metrics": self._metrics.to_dict()},
        )

    async def _drain(self) -> None:
        """Process all remaining events in the queue."""
        while not self._queue.empty():
            try:
                event_type, data = self._queue.get_nowait()
                await self._downstream.emit(type=event_type, data=data)
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

    async def _worker(self) -> None:
        """Background worker that processes events from the queue."""
        while self._running:
            try:
                event_type, data = await asyncio.wait_for(
                    self._queue.get(), timeout=0.1
                )
                try:
                    await self._downstream.emit(type=event_type, data=data)
                except Exception as e:
                    self._logger.error(
                        f"Failed to emit event to downstream: {e}",
                        extra={"event_type": event_type, "error": str(e)},
                    )
                finally:
                    self._queue.task_done()
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        """Emit an event asynchronously, blocking if queue is full."""
        if not self._running:
            await self.start()
        await self._queue.put((type, data))
        self._metrics.record_emit()

    def try_emit(self, *, type: str, data: dict[str, Any] | None) -> bool:
        """Emit an event without blocking.

        Returns:
            True if event was queued, False if dropped due to backpressure.
        """
        if not self._running:
            asyncio.create_task(self.start())

        try:
            self._queue.put_nowait((type, data))
            self._metrics.record_emit()
            return True
        except asyncio.QueueFull:
            self._metrics.record_drop()
            self._logger.warning(
                "Event dropped due to backpressure",
                extra={
                    "event_type": type,
                    "queue_size": self._queue.qsize(),
                    "dropped_total": self._metrics.dropped,
                },
            )
            if self._on_drop:
                self._on_drop(type, data)
            return False


_event_sink_var: ContextVar[EventSink | None] = ContextVar("event_sink", default=None)
_pending_emit_tasks: set[asyncio.Task[Any]] = set()


def set_event_sink(sink: EventSink) -> None:
    _event_sink_var.set(sink)


def clear_event_sink() -> None:
    _event_sink_var.set(None)


def get_event_sink() -> EventSink:
    return _event_sink_var.get() or NoOpEventSink()


async def wait_for_event_sink_tasks() -> None:
    """Await any pending event sink emit tasks (used in tests)."""

    if not _pending_emit_tasks:
        return

    pending = list(_pending_emit_tasks)
    try:
        await asyncio.gather(*pending, return_exceptions=True)
    finally:
        for task in pending:
            _pending_emit_tasks.discard(task)


__all__ = [
    "EventSink",
    "NoOpEventSink",
    "LoggingEventSink",
    "BackpressureAwareEventSink",
    "BackpressureMetrics",
    "set_event_sink",
    "clear_event_sink",
    "get_event_sink",
    "wait_for_event_sink_tasks",
]
