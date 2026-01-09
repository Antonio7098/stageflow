"""Tool errors for behavior gating, approval, and undo operations.

This module defines exceptions for tool execution failures following
the Single Responsibility Principle - each error type handles one failure mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


class ToolError(Exception):
    """Base exception for all tool-related errors."""

    def __init__(self, message: str, tool: str | None = None) -> None:
        self.tool = tool
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "tool": self.tool,
        }


class ToolNotFoundError(ToolError):
    """Raised when a tool is not registered for an action type."""

    def __init__(self, action_type: str) -> None:
        self.action_type = action_type
        super().__init__(
            f"No tool registered for action type: {action_type}",
            tool=action_type,
        )

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["action_type"] = self.action_type
        return result


class ToolDeniedError(ToolError):
    """Raised when a tool is denied due to behavior gating.

    This occurs when the current execution behavior is not in the tool's
    allowed_behaviors list.

    Attributes:
        tool: The tool name that was denied
        behavior: The current execution behavior
        allowed_behaviors: Behaviors that would allow this tool
    """

    def __init__(
        self,
        tool: str,
        behavior: str | None,
        allowed_behaviors: tuple[str, ...],
    ) -> None:
        self.behavior = behavior
        self.allowed_behaviors = allowed_behaviors
        message = (
            f"Tool '{tool}' denied: current behavior '{behavior}' "
            f"not in allowed behaviors {allowed_behaviors}"
        )
        super().__init__(message, tool=tool)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["behavior"] = self.behavior
        result["allowed_behaviors"] = list(self.allowed_behaviors)
        return result


class ToolApprovalDeniedError(ToolError):
    """Raised when HITL approval is denied for a tool execution.

    Attributes:
        tool: The tool that required approval
        request_id: The approval request ID
        reason: Reason for denial (user_denied, timeout, etc.)
    """

    def __init__(
        self,
        tool: str,
        request_id: UUID | None = None,
        reason: str = "user_denied",
    ) -> None:
        self.request_id = request_id
        self.reason = reason
        message = f"Tool '{tool}' approval denied: {reason}"
        super().__init__(message, tool=tool)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["request_id"] = str(self.request_id) if self.request_id else None
        result["reason"] = self.reason
        return result


class ToolApprovalTimeoutError(ToolApprovalDeniedError):
    """Raised when HITL approval times out."""

    def __init__(self, tool: str, request_id: UUID | None = None, timeout_seconds: float = 0) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(tool=tool, request_id=request_id, reason="timeout")

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["timeout_seconds"] = self.timeout_seconds
        return result


class ToolUndoError(ToolError):
    """Raised when an undo operation fails.

    Attributes:
        tool: The tool whose action was being undone
        action_id: The action ID that failed to undo
        reason: Reason for failure
    """

    def __init__(
        self,
        tool: str,
        action_id: UUID,
        reason: str,
    ) -> None:
        self.action_id = action_id
        self.reason = reason
        message = f"Failed to undo action '{action_id}' for tool '{tool}': {reason}"
        super().__init__(message, tool=tool)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["action_id"] = str(self.action_id)
        result["reason"] = self.reason
        return result


class ToolExecutionError(ToolError):
    """Raised when tool execution fails unexpectedly."""

    def __init__(
        self,
        tool: str,
        action_id: UUID | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.action_id = action_id
        self.cause = cause
        message = f"Tool '{tool}' execution failed"
        if cause:
            message += f": {cause}"
        super().__init__(message, tool=tool)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["action_id"] = str(self.action_id) if self.action_id else None
        result["cause"] = str(self.cause) if self.cause else None
        return result


__all__ = [
    "ToolError",
    "ToolNotFoundError",
    "ToolDeniedError",
    "ToolApprovalDeniedError",
    "ToolApprovalTimeoutError",
    "ToolUndoError",
    "ToolExecutionError",
]
