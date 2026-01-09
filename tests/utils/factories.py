"""Test data factories for stageflow tests."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from stageflow import Pipeline, PipelineContext, StageKind, StageOutput
from stageflow.tools import ToolDefinition, ToolInput, ToolOutput


def create_test_context(
    *,
    pipeline_run_id: UUID | None = None,
    request_id: UUID | None = None,
    session_id: UUID | None = None,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
    interaction_id: UUID | None = None,
    topology: str = "test_topology",
    execution_mode: str = "test",
    service: str = "test",
    data: dict[str, Any] | None = None,
    parent_run_id: UUID | None = None,
    parent_stage_id: str | None = None,
    correlation_id: UUID | None = None,
) -> PipelineContext:
    """Create a PipelineContext for testing.

    All IDs default to None unless specified. Use uuid4() to generate
    random IDs when needed.
    """
    return PipelineContext(
        pipeline_run_id=pipeline_run_id,
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        org_id=org_id,
        interaction_id=interaction_id,
        topology=topology,
        execution_mode=execution_mode,
        service=service,
        data=data or {},
        parent_run_id=parent_run_id,
        parent_stage_id=parent_stage_id,
        correlation_id=correlation_id,
    )


def create_test_stage(
    name: str = "test_stage",
    kind: StageKind = StageKind.TRANSFORM,
    output: StageOutput | None = None,
    should_fail: bool = False,
    fail_message: str = "Test failure",
) -> Any:
    """Create a mock stage for testing.

    Args:
        name: Stage name
        kind: Stage kind
        output: Output to return (defaults to StageOutput.ok())
        should_fail: If True, stage raises an exception
        fail_message: Error message if failing
    """
    from tests.utils.mocks import MockStage

    return MockStage(
        name=name,
        kind=kind,
        output=output or StageOutput.ok(),
        should_fail=should_fail,
        fail_message=fail_message,
    )


def create_test_pipeline(
    name: str = "test_pipeline",
    stages: list[tuple[str, StageKind]] | None = None,
) -> Pipeline:
    """Create a test pipeline with mock stages.

    Args:
        name: Pipeline name
        stages: List of (stage_name, kind) tuples. Defaults to 3 stages.
    """
    if stages is None:
        stages = [
            ("stage_a", StageKind.TRANSFORM),
            ("stage_b", StageKind.ENRICH),
            ("stage_c", StageKind.WORK),
        ]

    pipeline = Pipeline(name=name)
    for stage_name, kind in stages:
        stage = create_test_stage(name=stage_name, kind=kind)
        pipeline = pipeline.with_stage(stage_name, type(stage), kind)

    return pipeline


async def _simple_tool_handler(input: ToolInput) -> ToolOutput:
    """Simple tool handler that returns success."""
    return ToolOutput.ok(data={"action_id": str(input.action_id)})


async def _simple_undo_handler(metadata: Any) -> None:
    """Simple undo handler that does nothing."""
    pass


def create_test_tool_definition(
    name: str = "test_tool",
    action_type: str = "TEST_ACTION",
    allowed_behaviors: tuple[str, ...] = (),
    requires_approval: bool = False,
    undoable: bool = False,
    handler: Any = None,
    undo_handler: Any = None,
) -> ToolDefinition:
    """Create a ToolDefinition for testing.

    Args:
        name: Tool name
        action_type: Action type this tool handles
        allowed_behaviors: Behaviors allowed to use this tool
        requires_approval: Whether HITL approval is needed
        undoable: Whether actions can be undone
        handler: Custom handler (defaults to simple success handler)
        undo_handler: Custom undo handler
    """
    return ToolDefinition(
        name=name,
        action_type=action_type,
        handler=handler or _simple_tool_handler,
        allowed_behaviors=allowed_behaviors,
        requires_approval=requires_approval,
        undoable=undoable,
        undo_handler=undo_handler if undoable else None,
    )


__all__ = [
    "create_test_context",
    "create_test_stage",
    "create_test_pipeline",
    "create_test_tool_definition",
]
