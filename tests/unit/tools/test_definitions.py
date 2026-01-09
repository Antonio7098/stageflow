"""Unit tests for tool definitions."""

from __future__ import annotations

from uuid import uuid4

import pytest

from stageflow.tools import (
    ToolDefinition,
    ToolInput,
    ToolOutput,
    UndoMetadata,
)


class TestToolInput:
    """Tests for ToolInput dataclass."""

    def test_create_tool_input(self) -> None:
        """Create a ToolInput with all fields."""
        action_id = uuid4()
        input = ToolInput(
            action_id=action_id,
            tool_name="test_tool",
            payload={"key": "value"},
            behavior="practice",
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
        )
        assert input.action_id == action_id
        assert input.tool_name == "test_tool"
        assert input.payload == {"key": "value"}
        assert input.behavior == "practice"

    def test_tool_input_to_dict(self) -> None:
        """ToolInput serializes to dictionary."""
        action_id = uuid4()
        input = ToolInput(
            action_id=action_id,
            tool_name="test_tool",
            payload={"key": "value"},
        )
        result = input.to_dict()
        assert result["action_id"] == str(action_id)
        assert result["tool_name"] == "test_tool"
        assert result["payload"] == {"key": "value"}


class TestToolOutput:
    """Tests for ToolOutput dataclass."""

    def test_create_success_output(self) -> None:
        """Create a successful ToolOutput."""
        output = ToolOutput.ok(data={"result": "success"})
        assert output.success is True
        assert output.data == {"result": "success"}
        assert output.error is None

    def test_create_failure_output(self) -> None:
        """Create a failed ToolOutput."""
        output = ToolOutput.fail("Something went wrong")
        assert output.success is False
        assert output.error == "Something went wrong"
        assert output.data is None

    def test_output_with_artifacts(self) -> None:
        """ToolOutput can include artifacts."""
        artifacts = [{"type": "file", "path": "/tmp/test.txt"}]
        output = ToolOutput.ok(data={}, artifacts=artifacts)
        assert output.artifacts == artifacts

    def test_output_with_undo_metadata(self) -> None:
        """ToolOutput can include undo metadata."""
        undo_data = {"original_content": "hello"}
        output = ToolOutput.ok(data={}, undo_metadata=undo_data)
        assert output.undo_metadata == undo_data

    def test_output_to_dict(self) -> None:
        """ToolOutput serializes to dictionary."""
        output = ToolOutput.ok(data={"key": "value"})
        result = output.to_dict()
        assert result["success"] is True
        assert result["data"] == {"key": "value"}


class TestUndoMetadata:
    """Tests for UndoMetadata dataclass."""

    def test_create_undo_metadata(self) -> None:
        """Create UndoMetadata."""
        action_id = uuid4()
        metadata = UndoMetadata(
            action_id=action_id,
            tool_name="edit_document",
            undo_data={"original": "content"},
        )
        assert metadata.action_id == action_id
        assert metadata.tool_name == "edit_document"
        assert metadata.undo_data == {"original": "content"}

    def test_undo_metadata_to_dict(self) -> None:
        """UndoMetadata serializes to dictionary."""
        action_id = uuid4()
        metadata = UndoMetadata(
            action_id=action_id,
            tool_name="test_tool",
            undo_data={"key": "value"},
        )
        result = metadata.to_dict()
        assert result["action_id"] == str(action_id)
        assert result["tool_name"] == "test_tool"
        assert result["undo_data"] == {"key": "value"}
        assert "created_at" in result

    def test_undo_metadata_from_dict(self) -> None:
        """UndoMetadata deserializes from dictionary."""
        action_id = uuid4()
        data = {
            "action_id": str(action_id),
            "tool_name": "test_tool",
            "undo_data": {"key": "value"},
            "created_at": "2024-01-01T00:00:00Z",
        }
        metadata = UndoMetadata.from_dict(data)
        assert metadata.action_id == action_id
        assert metadata.tool_name == "test_tool"


class TestToolDefinition:
    """Tests for ToolDefinition dataclass."""

    async def _dummy_handler(self, input: ToolInput) -> ToolOutput:
        return ToolOutput.ok()

    def test_create_tool_definition(self) -> None:
        """Create a ToolDefinition with basic fields."""
        tool = ToolDefinition(
            name="test_tool",
            action_type="TEST_ACTION",
            handler=self._dummy_handler,
        )
        assert tool.name == "test_tool"
        assert tool.action_type == "TEST_ACTION"
        assert tool.allowed_behaviors == ()
        assert tool.requires_approval is False
        assert tool.undoable is False

    def test_tool_with_behavior_gating(self) -> None:
        """ToolDefinition with behavior restrictions."""
        tool = ToolDefinition(
            name="edit_tool",
            action_type="EDIT",
            handler=self._dummy_handler,
            allowed_behaviors=("doc_edit", "practice"),
        )
        assert tool.allowed_behaviors == ("doc_edit", "practice")
        assert tool.is_behavior_allowed("doc_edit") is True
        assert tool.is_behavior_allowed("practice") is True
        assert tool.is_behavior_allowed("roleplay") is False

    def test_empty_allowed_behaviors_allows_all(self) -> None:
        """Empty allowed_behaviors means all behaviors allowed."""
        tool = ToolDefinition(
            name="open_tool",
            action_type="OPEN",
            handler=self._dummy_handler,
            allowed_behaviors=(),
        )
        assert tool.is_behavior_allowed("any_behavior") is True
        assert tool.is_behavior_allowed(None) is True

    def test_tool_with_approval(self) -> None:
        """ToolDefinition with approval requirement."""
        tool = ToolDefinition(
            name="risky_tool",
            action_type="RISKY",
            handler=self._dummy_handler,
            requires_approval=True,
            approval_message="Are you sure?",
        )
        assert tool.requires_approval is True
        assert tool.approval_message == "Are you sure?"

    def test_tool_with_undo(self) -> None:
        """ToolDefinition with undo capability."""

        async def undo_handler(metadata: UndoMetadata) -> None:
            pass

        tool = ToolDefinition(
            name="undoable_tool",
            action_type="UNDOABLE",
            handler=self._dummy_handler,
            undoable=True,
            undo_handler=undo_handler,
        )
        assert tool.undoable is True
        assert tool.undo_handler is not None

    def test_tool_to_dict(self) -> None:
        """ToolDefinition serializes to dictionary (without handlers)."""
        tool = ToolDefinition(
            name="test_tool",
            action_type="TEST",
            handler=self._dummy_handler,
            allowed_behaviors=("test",),
            requires_approval=True,
        )
        result = tool.to_dict()
        assert result["name"] == "test_tool"
        assert result["action_type"] == "TEST"
        assert result["allowed_behaviors"] == ["test"]
        assert result["requires_approval"] is True
        assert "handler" not in result  # Handlers not serialized
