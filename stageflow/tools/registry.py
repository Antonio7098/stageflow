"""Tool registry for discovering and executing agent actions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from .base import Tool, ToolInput, ToolOutput


class ActionProtocol(Protocol):
    """Protocol for action objects."""

    @property
    def type(self) -> str:
        ...

    @property
    def payload(self) -> dict[str, Any]:
        ...


class ToolRegistry:
    """Registry for tools that can execute agent actions.

    The registry provides:
    - Tool discovery by action type
    - Registration of new tools
    - Execution of actions through their corresponding tools
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._factories: dict[str, Callable[..., Tool]] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        self._tools[tool.action_type] = tool

    def register_factory(self, action_type: str, factory: Callable[..., Tool]) -> None:
        """Register a factory for lazy tool creation."""
        self._factories[action_type] = factory

    def get_tool(self, action_type: str) -> Tool | None:
        """Get a tool for the given action type."""
        if action_type in self._tools:
            return self._tools[action_type]

        if action_type in self._factories:
            tool = self._factories[action_type]()
            self._tools[action_type] = tool
            return tool

        return None

    def can_execute(self, action_type: str) -> bool:
        """Check if we have a tool for this action type."""
        return action_type in self._tools or action_type in self._factories

    async def execute(self, action: ActionProtocol, ctx: dict[str, Any]) -> ToolOutput | None:
        """Execute an action using its registered tool."""
        tool = self.get_tool(action.type)
        if tool is None:
            return ToolOutput(
                success=False,
                error=f"No tool registered for action type: {action.type}",
            )

        input = ToolInput(action=action)
        return await tool.execute(input, ctx)

    def list_tools(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def __contains__(self, action_type: str) -> bool:
        return self.can_execute(action_type)


# Global registry instance
_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def tool(
    action_type: str,
    name: str | None = None,
    description: str | None = None,
) -> Callable[[type], type]:
    """Decorator to register a tool class.

    Usage:
        @tool("store_memory", name="memory_store", description="Store a memory")
        class MemoryStoreTool(BaseTool):
            ...
    """

    def decorator(cls: type) -> type:
        # Store metadata on the class
        cls._tool_action_type = action_type
        cls._tool_name = name or cls.__name__
        cls._tool_description = description or ""

        # Register with global registry
        registry = get_tool_registry()
        registry.register_factory(action_type, cls)

        return cls

    return decorator


def register_tool(tool_instance: Tool) -> None:
    """Register a tool instance with the global registry."""
    registry = get_tool_registry()
    registry.register(tool_instance)


__all__ = ["ToolRegistry", "get_tool_registry", "tool", "register_tool"]
