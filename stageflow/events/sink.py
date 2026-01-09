"""Event sink implementations for stageflow.

This module provides the EventSink protocol and default implementations:
- NoOpEventSink: Discards all events (default)
- LoggingEventSink: Logs events to Python logging
"""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
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
    "set_event_sink",
    "clear_event_sink",
    "get_event_sink",
    "wait_for_event_sink_tasks",
]
