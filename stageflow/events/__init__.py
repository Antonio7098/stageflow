"""Framework events module - exports framework event types."""

# Export event types from local sink module
# Add emit_event function locally
from typing import Any

from stageflow.events.sink import (
    BackpressureAwareEventSink,
    BackpressureMetrics,
    EventSink,
    LoggingEventSink,
    NoOpEventSink,
    clear_event_sink,
    get_event_sink,
    set_event_sink,
    wait_for_event_sink_tasks,
)


async def emit_event(*, type: str, data: dict[str, Any] | None) -> None:
    """Emit an event through the current event sink."""
    sink = get_event_sink()
    if hasattr(sink, "emit"):
        await sink.emit(type=type, data=data)


# Backward compatibility aliases
register_event_sink = set_event_sink

__all__ = [
    "BackpressureAwareEventSink",
    "BackpressureMetrics",
    "EventSink",
    "LoggingEventSink",
    "NoOpEventSink",
    "clear_event_sink",
    "get_event_sink",
    "set_event_sink",
    "wait_for_event_sink_tasks",
    "emit_event",
    "register_event_sink",
]
