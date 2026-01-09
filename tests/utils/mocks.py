"""Mock objects for stageflow tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from stageflow import StageKind, StageOutput
from stageflow.tools import ToolInput, ToolOutput


@dataclass
class MockEventSink:
    """Mock event sink that captures emitted events."""

    events: list[dict[str, Any]] = field(default_factory=list)
    _emit_count: int = 0

    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        """Capture emitted event."""
        self.events.append({"type": type, "data": data})
        self._emit_count += 1

    def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        """Capture emitted event (sync version)."""
        self.events.append({"type": type, "data": data})
        self._emit_count += 1

    def get_events_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """Get all events of a specific type."""
        return [e for e in self.events if e["type"] == event_type]

    def has_event(self, event_type: str) -> bool:
        """Check if an event of the given type was emitted."""
        return any(e["type"] == event_type for e in self.events)

    def clear(self) -> None:
        """Clear all captured events."""
        self.events.clear()
        self._emit_count = 0

    @property
    def emit_count(self) -> int:
        """Number of events emitted."""
        return self._emit_count


@dataclass
class MockStage:
    """Mock stage for testing pipeline execution."""

    name: str = "mock_stage"
    kind: StageKind = StageKind.TRANSFORM
    output: StageOutput = field(default_factory=StageOutput.ok)
    should_fail: bool = False
    fail_message: str = "Mock stage failure"
    execute_count: int = 0

    async def execute(self, _ctx: Any) -> StageOutput:
        """Execute the mock stage."""
        self.execute_count += 1
        if self.should_fail:
            raise RuntimeError(self.fail_message)
        return self.output


@dataclass
class MockAction:
    """Mock action for testing tool execution."""

    id: UUID
    type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class MockTool:
    """Mock tool for testing tool execution."""

    name: str = "mock_tool"
    action_type: str = "MOCK_ACTION"
    description: str = "A mock tool for testing"
    execute_count: int = 0
    last_input: ToolInput | None = None
    should_fail: bool = False
    fail_message: str = "Mock tool failure"
    output_data: dict[str, Any] = field(default_factory=dict)

    async def execute(self, input: ToolInput, _ctx: dict[str, Any]) -> ToolOutput:
        """Execute the mock tool."""
        self.execute_count += 1
        self.last_input = input
        if self.should_fail:
            return ToolOutput(success=False, error=self.fail_message)
        return ToolOutput(success=True, data=self.output_data)


__all__ = [
    "MockEventSink",
    "MockStage",
    "MockAction",
    "MockTool",
]
