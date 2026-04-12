"""Async lifecycle sinks for tool persistence and projection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from stageflow.events import get_event_sink


class ToolLifecycleSinkError(RuntimeError):
    """Raised when a lifecycle sink cannot record an event."""


@dataclass(frozen=True, slots=True)
class ToolLifecycleEvent:
    """Structured lifecycle event for tool persistence and projection."""

    event_type: str
    tool_name: str
    action_id: str | None = None
    call_id: str | None = None
    pipeline_run_id: str | None = None
    request_id: str | None = None
    parent_stage_id: str | None = None
    sequence: int | None = None
    emitted_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return the serializable event payload."""
        result: dict[str, Any] = {
            "tool_name": self.tool_name,
            "action_id": self.action_id,
            "call_id": self.call_id,
            "pipeline_run_id": self.pipeline_run_id,
            "request_id": self.request_id,
            "parent_stage_id": self.parent_stage_id,
            "sequence": self.sequence,
            "emitted_at": self.emitted_at,
        }
        result.update(self.payload)
        return result


class ToolLifecycleSink(Protocol):
    """Async contract for persisting or projecting tool lifecycle state."""

    async def emit(self, event: ToolLifecycleEvent) -> None:
        """Record one structured lifecycle event."""


class NoOpToolLifecycleSink:
    """Lifecycle sink that intentionally discards all events."""

    async def emit(self, event: ToolLifecycleEvent) -> None:  # noqa: ARG002
        return None


class InMemoryToolLifecycleSink:
    """Test sink that records all lifecycle events in memory."""

    def __init__(self) -> None:
        self.events: list[ToolLifecycleEvent] = []

    async def emit(self, event: ToolLifecycleEvent) -> None:
        self.events.append(event)


class CompositeToolLifecycleSink:
    """Fan-out sink that forwards events to multiple child sinks."""

    def __init__(self, *sinks: ToolLifecycleSink) -> None:
        self._sinks = tuple(sinks)

    async def emit(self, event: ToolLifecycleEvent) -> None:
        for sink in self._sinks:
            await sink.emit(event)


class SequencedToolLifecycleSink:
    """Wrap a sink and attach monotonic sequence numbers."""

    def __init__(self, sink: ToolLifecycleSink) -> None:
        self._sink = sink
        self._sequence = 0
        self._lock = asyncio.Lock()

    async def emit(self, event: ToolLifecycleEvent) -> None:
        async with self._lock:
            self._sequence += 1
            sequence = self._sequence
        await self._sink.emit(replace(event, sequence=sequence))


class EventSinkToolLifecycleSink:
    """Bridge tool lifecycle events into the configured Stageflow EventSink."""

    async def emit(self, event: ToolLifecycleEvent) -> None:
        sink = get_event_sink()
        try:
            await sink.emit(type=event.event_type, data=event.to_payload())
        except Exception as exc:  # pragma: no cover - depends on sink implementation
            raise ToolLifecycleSinkError(
                f"Failed to emit tool lifecycle event {event.event_type!r}"
            ) from exc


__all__ = [
    "CompositeToolLifecycleSink",
    "EventSinkToolLifecycleSink",
    "InMemoryToolLifecycleSink",
    "NoOpToolLifecycleSink",
    "SequencedToolLifecycleSink",
    "ToolLifecycleEvent",
    "ToolLifecycleSink",
    "ToolLifecycleSinkError",
]
