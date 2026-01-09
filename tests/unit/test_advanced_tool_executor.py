"""Tests for AdvancedToolExecutor with ExecutionContext."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest

from stageflow.context import ContextSnapshot
from stageflow.core import StageContext
from stageflow.events import NoOpEventSink
from stageflow.stages.context import PipelineContext
from stageflow.tools import (
    AdvancedToolExecutor,
    DictContextAdapter,
    ToolDefinition,
    ToolDeniedError,
    ToolExecutorConfig,
    ToolInput,
    ToolNotFoundError,
    ToolOutput,
)


@dataclass(frozen=True)
class MockAction:
    """Mock action for testing."""
    id: UUID
    type: str
    payload: dict[str, Any]


async def mock_handler(input: ToolInput) -> ToolOutput:
    """Simple mock handler that returns success."""
    return ToolOutput.ok(data={"handled": True, "payload": input.payload})


async def mock_failing_handler(_input: ToolInput) -> ToolOutput:
    """Mock handler that raises an exception."""
    raise ValueError("Handler failed")


class TestAdvancedToolExecutorWithStageContext:
    """Test AdvancedToolExecutor with StageContext."""

    @pytest.fixture
    def executor(self):
        """Create executor with events disabled for simpler testing."""
        return AdvancedToolExecutor(
            config=ToolExecutorConfig(emit_events=False)
        )

    @pytest.fixture
    def stage_context(self):
        """Create a StageContext for testing."""
        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test_topology",
            execution_mode="practice",
        )
        return StageContext(snapshot=snapshot)

    @pytest.mark.asyncio
    async def test_execute_with_stage_context(self, executor, stage_context):
        """Should execute tool with StageContext."""
        executor.register(ToolDefinition(
            name="test_tool",
            action_type="TEST_ACTION",
            handler=mock_handler,
        ))

        action = MockAction(
            id=uuid4(),
            type="TEST_ACTION",
            payload={"key": "value"},
        )

        result = await executor.execute(action, stage_context)

        assert result.success
        assert result.data["handled"] is True
        assert result.data["payload"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_behavior_gating_with_stage_context(self, executor, stage_context):
        """Should enforce behavior gating with StageContext."""
        executor.register(ToolDefinition(
            name="restricted_tool",
            action_type="RESTRICTED_ACTION",
            handler=mock_handler,
            allowed_behaviors=("doc_edit",),  # Not "practice"
        ))

        action = MockAction(
            id=uuid4(),
            type="RESTRICTED_ACTION",
            payload={},
        )

        with pytest.raises(ToolDeniedError) as exc_info:
            await executor.execute(action, stage_context)

        assert exc_info.value.tool == "restricted_tool"
        assert exc_info.value.behavior == "practice"

    @pytest.mark.asyncio
    async def test_behavior_gating_allowed(self, executor):
        """Should allow tool when behavior matches."""
        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
            topology=None,
            execution_mode="doc_edit",
        )
        ctx = StageContext(snapshot=snapshot)

        executor.register(ToolDefinition(
            name="doc_tool",
            action_type="DOC_ACTION",
            handler=mock_handler,
            allowed_behaviors=("doc_edit", "practice"),
        ))

        action = MockAction(
            id=uuid4(),
            type="DOC_ACTION",
            payload={},
        )

        result = await executor.execute(action, ctx)
        assert result.success


class TestAdvancedToolExecutorWithPipelineContext:
    """Test AdvancedToolExecutor with PipelineContext."""

    @pytest.fixture
    def executor(self):
        """Create executor with events disabled."""
        return AdvancedToolExecutor(
            config=ToolExecutorConfig(emit_events=False)
        )

    @pytest.fixture
    def pipeline_context(self):
        """Create a PipelineContext for testing."""
        return PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            execution_mode="roleplay",
            event_sink=NoOpEventSink(),
        )

    @pytest.mark.asyncio
    async def test_execute_with_pipeline_context(self, executor, pipeline_context):
        """Should execute tool with PipelineContext."""
        executor.register(ToolDefinition(
            name="test_tool",
            action_type="TEST_ACTION",
            handler=mock_handler,
        ))

        action = MockAction(
            id=uuid4(),
            type="TEST_ACTION",
            payload={"key": "value"},
        )

        result = await executor.execute(action, pipeline_context)

        assert result.success
        assert result.data["handled"] is True

    @pytest.mark.asyncio
    async def test_behavior_gating_with_pipeline_context(self, executor, pipeline_context):
        """Should enforce behavior gating with PipelineContext."""
        executor.register(ToolDefinition(
            name="practice_only",
            action_type="PRACTICE_ACTION",
            handler=mock_handler,
            allowed_behaviors=("practice",),  # Not "roleplay"
        ))

        action = MockAction(
            id=uuid4(),
            type="PRACTICE_ACTION",
            payload={},
        )

        with pytest.raises(ToolDeniedError):
            await executor.execute(action, pipeline_context)


class TestAdvancedToolExecutorWithDictContext:
    """Test AdvancedToolExecutor with DictContextAdapter."""

    @pytest.fixture
    def executor(self):
        """Create executor with events disabled."""
        return AdvancedToolExecutor(
            config=ToolExecutorConfig(emit_events=False)
        )

    @pytest.fixture
    def dict_context(self):
        """Create a DictContextAdapter for testing."""
        return DictContextAdapter({
            "pipeline_run_id": str(uuid4()),
            "request_id": str(uuid4()),
            "execution_mode": "practice",
        })

    @pytest.mark.asyncio
    async def test_execute_with_dict_context(self, executor, dict_context):
        """Should execute tool with DictContextAdapter."""
        executor.register(ToolDefinition(
            name="test_tool",
            action_type="TEST_ACTION",
            handler=mock_handler,
        ))

        action = MockAction(
            id=uuid4(),
            type="TEST_ACTION",
            payload={"key": "value"},
        )

        result = await executor.execute(action, dict_context)

        assert result.success
        assert result.data["handled"] is True

    @pytest.mark.asyncio
    async def test_behavior_gating_with_dict_context(self, executor, dict_context):
        """Should enforce behavior gating with DictContextAdapter."""
        executor.register(ToolDefinition(
            name="restricted_tool",
            action_type="RESTRICTED_ACTION",
            handler=mock_handler,
            allowed_behaviors=("doc_edit",),  # Not "practice"
        ))

        action = MockAction(
            id=uuid4(),
            type="RESTRICTED_ACTION",
            payload={},
        )

        with pytest.raises(ToolDeniedError):
            await executor.execute(action, dict_context)


class TestAdvancedToolExecutorErrors:
    """Test error handling in AdvancedToolExecutor."""

    @pytest.fixture
    def executor(self):
        """Create executor with events disabled."""
        return AdvancedToolExecutor(
            config=ToolExecutorConfig(emit_events=False)
        )

    @pytest.fixture
    def context(self):
        """Create a context for testing."""
        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
            topology=None,
            execution_mode=None,
        )
        return StageContext(snapshot=snapshot)

    @pytest.mark.asyncio
    async def test_tool_not_found(self, executor, context):
        """Should raise ToolNotFoundError for unknown action type."""
        action = MockAction(
            id=uuid4(),
            type="UNKNOWN_ACTION",
            payload={},
        )

        with pytest.raises(ToolNotFoundError) as exc_info:
            await executor.execute(action, context)

        assert "UNKNOWN_ACTION" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_behaviors_allows_all(self, executor, context):
        """Empty allowed_behaviors should allow all behaviors."""
        executor.register(ToolDefinition(
            name="universal_tool",
            action_type="UNIVERSAL_ACTION",
            handler=mock_handler,
            allowed_behaviors=(),  # Empty = all allowed
        ))

        action = MockAction(
            id=uuid4(),
            type="UNIVERSAL_ACTION",
            payload={},
        )

        result = await executor.execute(action, context)
        assert result.success


class TestToolInputFromAction:
    """Test ToolInput.from_action with different context types."""

    def test_from_action_with_stage_context(self):
        """Should create ToolInput from StageContext."""
        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
            topology=None,
            execution_mode="practice",
        )
        ctx = StageContext(snapshot=snapshot)

        action = MockAction(
            id=uuid4(),
            type="TEST_ACTION",
            payload={"key": "value"},
        )

        tool_input = ToolInput.from_action(action, "test_tool", ctx)

        assert tool_input.action_id == action.id
        assert tool_input.tool_name == "test_tool"
        assert tool_input.payload == {"key": "value"}
        assert tool_input.behavior == "practice"
        assert tool_input.pipeline_run_id == snapshot.pipeline_run_id
        assert tool_input.request_id == snapshot.request_id

    def test_from_action_with_pipeline_context(self):
        """Should create ToolInput from PipelineContext."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
            execution_mode="roleplay",
        )

        action = MockAction(
            id=uuid4(),
            type="TEST_ACTION",
            payload={"key": "value"},
        )

        tool_input = ToolInput.from_action(action, "test_tool", ctx)

        assert tool_input.behavior == "roleplay"
        assert tool_input.pipeline_run_id == ctx.pipeline_run_id

    def test_from_action_with_dict_context(self):
        """Should create ToolInput from DictContextAdapter."""
        run_id = uuid4()
        ctx = DictContextAdapter({
            "pipeline_run_id": str(run_id),
            "execution_mode": "doc_edit",
        })

        action = MockAction(
            id=uuid4(),
            type="TEST_ACTION",
            payload={},
        )

        tool_input = ToolInput.from_action(action, "test_tool", ctx)

        assert tool_input.behavior == "doc_edit"
        assert tool_input.pipeline_run_id == run_id

    def test_from_action_without_context(self):
        """Should create ToolInput without context."""
        action = MockAction(
            id=uuid4(),
            type="TEST_ACTION",
            payload={"key": "value"},
        )

        tool_input = ToolInput.from_action(action, "test_tool", None)

        assert tool_input.action_id == action.id
        assert tool_input.behavior is None
        assert tool_input.pipeline_run_id is None
        assert tool_input.request_id is None
