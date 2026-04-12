"""Tool protocol and base types for agent actions."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

from .runtime_io import NullToolRuntimeIO, ToolChildRun, ToolRuntimeIO
from .schema import ToolSchemaError

class ActionProtocol(Protocol):
    """Protocol for action objects."""

    @property
    def type(self) -> str:
        ...

    @property
    def payload(self) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class ToolInput:
    """Input schema for a tool - wrapped action payload."""

    action: ActionProtocol
    runtime: ToolRuntimeIO = NullToolRuntimeIO()

    async def publish_update(self, payload: dict[str, Any]) -> None:
        """Emit a structured progress update for the running tool."""
        await self.runtime.publish_update(payload)

    async def spawn_subpipeline(
        self,
        *,
        pipeline_name: str,
        correlation_id: Any | None = None,
        topology_override: str | None = None,
        execution_mode_override: str | None = None,
    ) -> ToolChildRun:
        """Spawn a child pipeline from the running tool."""
        return await self.runtime.spawn_subpipeline(
            pipeline_name=pipeline_name,
            correlation_id=correlation_id,
            topology_override=topology_override,
            execution_mode_override=execution_mode_override,
        )


@dataclass(frozen=True)
class ToolOutput:
    """Output from tool execution."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    artifacts: list[dict[str, Any]] | None = None
    child_runs: list[ToolChildRun] | None = None


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

    @property
    def input_model(self) -> type[BaseModel] | None:
        """Optional Pydantic model for typed provider tool arguments."""
        return None

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema for provider-native tool calling."""
        input_model = self.input_model
        if input_model is not None:
            if not isinstance(input_model, type) or not issubclass(input_model, BaseModel):
                raise ToolSchemaError(
                    f"Tool {self.name!r} input_model must be a Pydantic BaseModel subclass"
                )
            return input_model.model_json_schema()
        return {"type": "object", "properties": {}}

    async def execute(self, input: ToolInput, ctx: dict[str, Any]) -> ToolOutput:
        """Execute the tool with the given input and context."""
        raise NotImplementedError(f"Tool {self.name} must implement execute()")

    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"


__all__ = ["Tool", "ToolInput", "ToolOutput", "BaseTool"]
