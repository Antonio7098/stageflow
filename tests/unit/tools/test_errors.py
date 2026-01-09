"""Unit tests for tool errors."""

from __future__ import annotations

from uuid import uuid4

from stageflow.tools import (
    ToolApprovalDeniedError,
    ToolApprovalTimeoutError,
    ToolDeniedError,
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolUndoError,
)


class TestToolError:
    """Tests for base ToolError."""

    def test_create_tool_error(self) -> None:
        """Create a basic ToolError."""
        error = ToolError("Something went wrong", tool="test_tool")
        assert str(error) == "Something went wrong"
        assert error.tool == "test_tool"

    def test_tool_error_to_dict(self) -> None:
        """ToolError serializes to dictionary."""
        error = ToolError("Test error", tool="my_tool")
        result = error.to_dict()
        assert result["error_type"] == "ToolError"
        assert result["message"] == "Test error"
        assert result["tool"] == "my_tool"


class TestToolNotFoundError:
    """Tests for ToolNotFoundError."""

    def test_create_not_found_error(self) -> None:
        """Create ToolNotFoundError."""
        error = ToolNotFoundError("UNKNOWN_ACTION")
        assert "UNKNOWN_ACTION" in str(error)
        assert error.action_type == "UNKNOWN_ACTION"

    def test_not_found_error_to_dict(self) -> None:
        """ToolNotFoundError includes action_type."""
        error = ToolNotFoundError("MISSING")
        result = error.to_dict()
        assert result["action_type"] == "MISSING"


class TestToolDeniedError:
    """Tests for ToolDeniedError."""

    def test_create_denied_error(self) -> None:
        """Create ToolDeniedError."""
        error = ToolDeniedError(
            tool="edit_document",
            behavior="roleplay",
            allowed_behaviors=("doc_edit", "practice"),
        )
        assert "edit_document" in str(error)
        assert "roleplay" in str(error)
        assert error.behavior == "roleplay"
        assert error.allowed_behaviors == ("doc_edit", "practice")

    def test_denied_error_to_dict(self) -> None:
        """ToolDeniedError serializes correctly."""
        error = ToolDeniedError(
            tool="test",
            behavior="forbidden",
            allowed_behaviors=("allowed",),
        )
        result = error.to_dict()
        assert result["behavior"] == "forbidden"
        assert result["allowed_behaviors"] == ["allowed"]


class TestToolApprovalDeniedError:
    """Tests for ToolApprovalDeniedError."""

    def test_create_approval_denied_error(self) -> None:
        """Create ToolApprovalDeniedError."""
        request_id = uuid4()
        error = ToolApprovalDeniedError(
            tool="risky_tool",
            request_id=request_id,
            reason="user_denied",
        )
        assert "risky_tool" in str(error)
        assert error.request_id == request_id
        assert error.reason == "user_denied"

    def test_approval_denied_to_dict(self) -> None:
        """ToolApprovalDeniedError serializes correctly."""
        request_id = uuid4()
        error = ToolApprovalDeniedError(
            tool="test",
            request_id=request_id,
        )
        result = error.to_dict()
        assert result["request_id"] == str(request_id)
        assert result["reason"] == "user_denied"


class TestToolApprovalTimeoutError:
    """Tests for ToolApprovalTimeoutError."""

    def test_create_timeout_error(self) -> None:
        """Create ToolApprovalTimeoutError."""
        error = ToolApprovalTimeoutError(
            tool="slow_tool",
            timeout_seconds=60.0,
        )
        assert error.reason == "timeout"
        assert error.timeout_seconds == 60.0

    def test_timeout_error_to_dict(self) -> None:
        """ToolApprovalTimeoutError includes timeout_seconds."""
        error = ToolApprovalTimeoutError(tool="test", timeout_seconds=30.0)
        result = error.to_dict()
        assert result["timeout_seconds"] == 30.0


class TestToolUndoError:
    """Tests for ToolUndoError."""

    def test_create_undo_error(self) -> None:
        """Create ToolUndoError."""
        action_id = uuid4()
        error = ToolUndoError(
            tool="edit_document",
            action_id=action_id,
            reason="Document was modified",
        )
        assert str(action_id) in str(error)
        assert error.action_id == action_id
        assert error.reason == "Document was modified"

    def test_undo_error_to_dict(self) -> None:
        """ToolUndoError serializes correctly."""
        action_id = uuid4()
        error = ToolUndoError(
            tool="test",
            action_id=action_id,
            reason="test reason",
        )
        result = error.to_dict()
        assert result["action_id"] == str(action_id)
        assert result["reason"] == "test reason"


class TestToolExecutionError:
    """Tests for ToolExecutionError."""

    def test_create_execution_error(self) -> None:
        """Create ToolExecutionError."""
        action_id = uuid4()
        cause = ValueError("Bad input")
        error = ToolExecutionError(
            tool="test_tool",
            action_id=action_id,
            cause=cause,
        )
        assert "test_tool" in str(error)
        assert error.action_id == action_id
        assert error.cause is cause

    def test_execution_error_to_dict(self) -> None:
        """ToolExecutionError serializes correctly."""
        error = ToolExecutionError(
            tool="test",
            cause=RuntimeError("Something broke"),
        )
        result = error.to_dict()
        assert "Something broke" in result["cause"]
