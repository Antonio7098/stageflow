"""Enhanced tool definitions with behavior gating, undo, and approval support.

This module provides the ToolDefinition dataclass and related types for
configuring advanced tool capabilities including:
- Behavior gating (restricting tools to specific execution modes)
- Undo semantics (reversible actions)
- HITL approval flow (human-in-the-loop for risky actions)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from stageflow.protocols import ExecutionContext


class Action(Protocol):
    """Protocol for action objects passed to tools."""

    @property
    def id(self) -> UUID:
        """Unique action identifier."""
        ...

    @property
    def type(self) -> str:
        """Action type string."""
        ...

    @property
    def payload(self) -> dict[str, Any]:
        """Action payload data."""
        ...


@dataclass(frozen=True, slots=True)
class ToolInput:
    """Input schema for a tool - wrapped action with context.

    Attributes:
        action_id: Unique identifier for the action
        tool_name: Name of the tool being invoked
        payload: Action payload data
        behavior: Current execution behavior/mode
        pipeline_run_id: Pipeline run identifier for correlation
        request_id: Request identifier for tracing
    """

    action_id: UUID
    tool_name: str
    payload: dict[str, Any]
    behavior: str | None = None
    pipeline_run_id: UUID | None = None
    request_id: UUID | None = None

    @classmethod
    def from_action(
        cls,
        action: Action,
        tool_name: str,
        ctx: ExecutionContext | None = None,
    ) -> ToolInput:
        """Create ToolInput from an Action and context.

        Args:
            action: The action to wrap
            tool_name: Name of the tool handling this action
            ctx: Optional execution context for correlation IDs

        Returns:
            ToolInput instance
        """
        return cls(
            action_id=action.id,
            tool_name=tool_name,
            payload=action.payload,
            behavior=ctx.execution_mode if ctx else None,
            pipeline_run_id=ctx.pipeline_run_id if ctx else None,
            request_id=ctx.request_id if ctx else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "action_id": str(self.action_id),
            "tool_name": self.tool_name,
            "payload": self.payload,
            "behavior": self.behavior,
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "request_id": str(self.request_id) if self.request_id else None,
        }


@dataclass(frozen=True, slots=True)
class UndoMetadata:
    """Metadata stored for undoable actions.

    Attributes:
        action_id: The action this undo data is for
        tool_name: Name of the tool that executed the action
        undo_data: Tool-specific data needed to reverse the action
        created_at: When the original action was executed
    """

    action_id: UUID
    tool_name: str
    undo_data: dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "action_id": str(self.action_id),
            "tool_name": self.tool_name,
            "undo_data": self.undo_data,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UndoMetadata:
        """Create from dictionary."""
        return cls(
            action_id=UUID(data["action_id"]),
            tool_name=data["tool_name"],
            undo_data=data["undo_data"],
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
        )


@dataclass(frozen=True, slots=True)
class ToolOutput:
    """Output from tool execution.

    Attributes:
        success: Whether the tool executed successfully
        data: Output data from the tool
        error: Error message if failed
        artifacts: List of artifacts produced
        undo_metadata: Data needed to undo this action (if undoable)
    """

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    artifacts: list[dict[str, Any]] | None = None
    undo_metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {"success": self.success}
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        if self.artifacts is not None:
            result["artifacts"] = self.artifacts
        if self.undo_metadata is not None:
            result["undo_metadata"] = self.undo_metadata
        return result

    @classmethod
    def ok(
        cls,
        data: dict[str, Any] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
        undo_metadata: dict[str, Any] | None = None,
    ) -> ToolOutput:
        """Create a successful output."""
        return cls(
            success=True,
            data=data,
            artifacts=artifacts,
            undo_metadata=undo_metadata,
        )

    @classmethod
    def fail(cls, error: str) -> ToolOutput:
        """Create a failed output."""
        return cls(success=False, error=error)


# Type aliases for tool handlers
ToolHandler = Callable[[ToolInput], Awaitable[ToolOutput]]
UndoHandler = Callable[[UndoMetadata], Awaitable[None]]


@dataclass(frozen=True)
class ToolDefinition:
    """Definition of a tool capability with gating, undo, and approval.

    This is the enhanced tool definition that supports:
    - Behavior gating: restricting tools to specific execution modes
    - Undo semantics: reversible actions with undo handlers
    - HITL approval: human-in-the-loop for risky actions

    Attributes:
        name: Unique tool identifier
        action_type: The action type this tool handles
        description: Human-readable description
        input_schema: JSON Schema for input validation
        handler: Async function to execute the tool
        allowed_behaviors: Tuple of behaviors that can use this tool
                          Empty tuple means all behaviors allowed
        requires_approval: Whether HITL approval is needed
        approval_message: Message to show in approval UI
        undoable: Whether this tool's actions can be undone
        undo_handler: Async function to reverse the action
        artifact_type: Type of artifact this tool produces
    """

    name: str
    action_type: str
    handler: ToolHandler
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    allowed_behaviors: tuple[str, ...] = ()
    requires_approval: bool = False
    approval_message: str | None = None
    undoable: bool = False
    undo_handler: UndoHandler | None = None
    artifact_type: str | None = None

    def is_behavior_allowed(self, behavior: str | None) -> bool:
        """Check if a behavior is allowed to use this tool.

        Args:
            behavior: The current execution behavior/mode

        Returns:
            True if behavior is allowed, False otherwise
        """
        if not self.allowed_behaviors:
            return True
        return behavior in self.allowed_behaviors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization (without handlers)."""
        return {
            "name": self.name,
            "action_type": self.action_type,
            "description": self.description,
            "input_schema": self.input_schema,
            "allowed_behaviors": list(self.allowed_behaviors),
            "requires_approval": self.requires_approval,
            "approval_message": self.approval_message,
            "undoable": self.undoable,
            "artifact_type": self.artifact_type,
        }


__all__ = [
    "Action",
    "ToolInput",
    "ToolOutput",
    "ToolDefinition",
    "ToolHandler",
    "UndoHandler",
    "UndoMetadata",
]
