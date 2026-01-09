"""Tool event types for observability.

This module defines structured event types for the tool execution lifecycle,
enabling full observability of tool invocations, completions, and failures.

Event Flow:
    tool.invoked    → Action received, tool lookup complete
    tool.started    → Execution beginning
    tool.completed  → Success, output available
    tool.failed     → Error during execution
    tool.denied     → Behavior gating or approval denied
    tool.undone     → Action reversed via undo
    tool.undo_failed → Undo attempt failed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ToolEventBase:
    """Base class for all tool events."""

    tool_name: str
    action_id: UUID
    pipeline_run_id: UUID | None = None
    request_id: UUID | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def _base_dict(self) -> dict[str, Any]:
        """Get base event fields as dictionary."""
        return {
            "tool_name": self.tool_name,
            "action_id": str(self.action_id),
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "request_id": str(self.request_id) if self.request_id else None,
            "timestamp": self.timestamp,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for emission."""
        return self._base_dict()


@dataclass(frozen=True)
class ToolInvokedEvent(ToolEventBase):
    """Emitted when an action is received and tool lookup is complete."""

    payload_summary: dict[str, Any] = field(default_factory=dict)
    behavior: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = self._base_dict()
        result["payload_summary"] = self.payload_summary
        result["behavior"] = self.behavior
        return result


@dataclass(frozen=True)
class ToolStartedEvent(ToolEventBase):
    """Emitted when tool execution begins."""

    def to_dict(self) -> dict[str, Any]:
        return self._base_dict()


@dataclass(frozen=True)
class ToolCompletedEvent(ToolEventBase):
    """Emitted when tool execution completes successfully."""

    duration_ms: float = 0.0
    output_summary: dict[str, Any] = field(default_factory=dict)
    artifacts_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        result = self._base_dict()
        result["duration_ms"] = self.duration_ms
        result["output_summary"] = self.output_summary
        result["artifacts_count"] = self.artifacts_count
        return result


@dataclass(frozen=True)
class ToolFailedEvent(ToolEventBase):
    """Emitted when tool execution fails."""

    duration_ms: float = 0.0
    error_code: str = "execution_error"
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = self._base_dict()
        result["duration_ms"] = self.duration_ms
        result["error_code"] = self.error_code
        result["error_message"] = self.error_message
        return result


@dataclass(frozen=True)
class ToolDeniedEvent(ToolEventBase):
    """Emitted when tool execution is denied."""

    reason: str = ""
    behavior: str | None = None
    allowed_behaviors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = self._base_dict()
        result["reason"] = self.reason
        result["behavior"] = self.behavior
        result["allowed_behaviors"] = list(self.allowed_behaviors)
        return result


@dataclass(frozen=True)
class ToolUndoneEvent(ToolEventBase):
    """Emitted when a tool action is successfully undone."""

    duration_ms: float = 0.0
    original_action_timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = self._base_dict()
        result["duration_ms"] = self.duration_ms
        result["original_action_timestamp"] = self.original_action_timestamp
        return result


@dataclass(frozen=True)
class ToolUndoFailedEvent(ToolEventBase):
    """Emitted when an undo attempt fails."""

    error_message: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = self._base_dict()
        result["error_message"] = self.error_message
        result["reason"] = self.reason
        return result


# HITL Approval Events


@dataclass(frozen=True)
class ApprovalRequestedEvent:
    """Emitted when HITL approval is requested for a tool."""

    request_id: UUID
    tool_name: str
    action_id: UUID
    pipeline_run_id: UUID | None = None
    approval_message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": str(self.request_id),
            "tool_name": self.tool_name,
            "action_id": str(self.action_id),
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "approval_message": self.approval_message,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class ApprovalDecidedEvent:
    """Emitted when HITL approval decision is made."""

    request_id: UUID
    tool_name: str
    action_id: UUID
    decision: str  # "approved" or "denied"
    decided_by: UUID | None = None
    pipeline_run_id: UUID | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": str(self.request_id),
            "tool_name": self.tool_name,
            "action_id": str(self.action_id),
            "decision": self.decision,
            "decided_by": str(self.decided_by) if self.decided_by else None,
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "timestamp": self.timestamp,
        }


__all__ = [
    "ToolEventBase",
    "ToolInvokedEvent",
    "ToolStartedEvent",
    "ToolCompletedEvent",
    "ToolFailedEvent",
    "ToolDeniedEvent",
    "ToolUndoneEvent",
    "ToolUndoFailedEvent",
    "ApprovalRequestedEvent",
    "ApprovalDecidedEvent",
]
