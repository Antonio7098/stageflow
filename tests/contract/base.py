"""Base class and utilities for contract tests.

Contract tests verify that all stages comply with the Stage protocol,
ensuring consistent event emission and output structure.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from stageflow import PipelineContext, StageOutput
from tests.utils.mocks import MockEventSink


class StageProtocol(Protocol):
    """Protocol that all stages must implement."""

    name: str

    async def execute(self, ctx: PipelineContext) -> StageOutput:
        """Execute the stage."""
        ...


def create_contract_test_context(
    event_sink: MockEventSink | None = None,
) -> PipelineContext:
    """Create a PipelineContext configured for contract testing.

    Args:
        event_sink: Optional mock event sink (creates one if not provided)

    Returns:
        PipelineContext with mock event sink for event capture
    """
    sink = event_sink or MockEventSink()
    return PipelineContext(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=uuid4(),
        interaction_id=uuid4(),
        topology="contract_test",
        execution_mode="test",
        service="contract_test",
        event_sink=sink,
    )


def get_emitted_events(ctx: PipelineContext) -> list[dict[str, Any]]:
    """Get all events emitted through the context's event sink.

    Args:
        ctx: PipelineContext with MockEventSink

    Returns:
        List of emitted events
    """
    sink = ctx.event_sink
    if isinstance(sink, MockEventSink):
        return sink.events
    return []


def assert_event_emitted(
    ctx: PipelineContext,
    event_type: str,
    *,
    data_contains: dict[str, Any] | None = None,
) -> None:
    """Assert that an event of the given type was emitted.

    Args:
        ctx: PipelineContext with MockEventSink
        event_type: Event type to look for
        data_contains: Optional data fields that must be present

    Raises:
        AssertionError: If event not found or data doesn't match
    """
    events = get_emitted_events(ctx)
    matching = [e for e in events if e["type"] == event_type]

    assert len(matching) > 0, (
        f"Event '{event_type}' not emitted. "
        f"Emitted types: {[e['type'] for e in events]}"
    )

    if data_contains:
        event = matching[0]
        event_data = event.get("data", {}) or {}
        for key, value in data_contains.items():
            assert key in event_data, (
                f"Event '{event_type}' missing key '{key}'"
            )
            assert event_data[key] == value, (
                f"Event '{event_type}' key '{key}': expected {value}, got {event_data[key]}"
            )


class StageContractTest:
    """Base class for stage contract tests.

    Subclasses should implement get_stage() to return the stage to test.
    All contract test methods will then be run against that stage.
    """

    def get_stage(self) -> StageProtocol:
        """Return the stage to test. Override in subclass."""
        raise NotImplementedError("Subclass must implement get_stage()")

    async def test_has_name_attribute(self) -> None:
        """Stage must have a name attribute."""
        stage = self.get_stage()
        assert hasattr(stage, "name"), "Stage missing 'name' attribute"
        assert isinstance(stage.name, str), "Stage name must be a string"
        assert len(stage.name) > 0, "Stage name must not be empty"

    async def test_has_execute_method(self) -> None:
        """Stage must have an execute method."""
        stage = self.get_stage()
        assert hasattr(stage, "execute"), "Stage missing 'execute' method"
        assert callable(stage.execute), "Stage execute must be callable"

    async def test_execute_returns_stage_output(self) -> None:
        """Stage.execute() must return a StageOutput."""
        stage = self.get_stage()
        sink = MockEventSink()
        ctx = create_contract_test_context(sink)

        result = await stage.execute(ctx)

        assert isinstance(result, StageOutput), (
            f"Stage.execute() returned {type(result)}, expected StageOutput"
        )

    async def test_stage_output_has_valid_status(self) -> None:
        """StageOutput must have a valid status field."""
        stage = self.get_stage()
        sink = MockEventSink()
        ctx = create_contract_test_context(sink)

        result = await stage.execute(ctx)

        assert hasattr(result, "status"), "StageOutput missing 'status'"
        # Status should be one of the valid values
        valid_statuses = {"ok", "error", "skipped", "completed", "failed"}
        assert result.status in valid_statuses or hasattr(result.status, "value"), (
            f"Invalid status: {result.status}"
        )


__all__ = [
    "StageProtocol",
    "StageContractTest",
    "create_contract_test_context",
    "get_emitted_events",
    "assert_event_emitted",
]
