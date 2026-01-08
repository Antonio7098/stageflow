"""Tool protocol and base types for agent actions."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.ai.framework.agent.types import Action


@dataclass(frozen=True)
class ToolInput:
    """Input schema for a tool - wrapped action payload."""

    action: Action


@dataclass(frozen=True)
class ToolOutput:
    """Output from tool execution."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    artifacts: list[dict[str, Any]] | None = None


class Tool(Protocol):
    """Self-describing capability unit.

    Tools are the execution layer for agent actions. Each tool:
    - Has a unique name
    - Documents its input schema
    - Executes and returns structured output
    - Is registered in the ToolRegistry for discovery
    """

    @property
    def name(self) -> str:
        """Unique identifier for this tool."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description of what this tool does."""
        ...

    @property
    def action_type(self) -> str:
        """The action type string this tool handles."""
        ...

    async def execute(self, input: ToolInput, ctx: dict[str, Any]) -> ToolOutput:
        """Execute the tool with the given input and context.

        Args:
            input: Wrapped action containing type and payload
            ctx: Pipeline context including user, session, etc.

        Returns:
            ToolOutput with success status and any data/artifacts
        """
        ...


class BaseTool:
    """Base class for implementing tools (alternative to Protocol)."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique identifier for this tool."""
        ...

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Human-readable description of what this tool does."""
        ...

    @property
    @abc.abstractmethod
    def action_type(self) -> str:
        """The action type string this tool handles."""
        ...

    async def execute(self, input: ToolInput, ctx: dict[str, Any]) -> ToolOutput:
        """Execute the tool with the given input and context."""
        raise NotImplementedError(f"Tool {self.name} must implement execute()")

    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"


__all__ = ["Tool", "ToolInput", "ToolOutput", "BaseTool"]
