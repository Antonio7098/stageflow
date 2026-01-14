"""Tool registry for discovering and executing agent actions."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from .base import Tool, ToolInput, ToolOutput


@dataclass(frozen=True, slots=True)
class ResolvedToolCall:
    """A parsed tool call resolved to its registered tool.

    Attributes:
        tool: The resolved Tool instance.
        call_id: Original tool call ID from the provider.
        name: Tool name as specified in the call.
        arguments: Parsed arguments dictionary.
        raw: Original tool call data for debugging.
    """

    tool: Tool
    call_id: str
    name: str
    arguments: dict[str, Any]
    raw: Any = None


@dataclass(frozen=True, slots=True)
class UnresolvedToolCall:
    """A tool call that could not be resolved to a registered tool.

    Attributes:
        call_id: Original tool call ID from the provider.
        name: Tool name that was not found.
        arguments: Parsed arguments dictionary.
        error: Description of why resolution failed.
        raw: Original tool call data for debugging.
    """

    call_id: str
    name: str
    arguments: dict[str, Any]
    error: str
    raw: Any = None


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

    def parse_and_resolve(
        self,
        tool_calls: list[dict[str, Any]],
        *,
        id_field: str = "id",
        name_field: str = "name",
        arguments_field: str = "arguments",
        function_wrapper: str | None = "function",
    ) -> tuple[list[ResolvedToolCall], list[UnresolvedToolCall]]:
        """Parse tool calls and resolve them to registered tools.

        Handles common tool call formats from LLM providers (OpenAI, Anthropic, etc.)
        and resolves tool names to registered tools in the registry.

        Args:
            tool_calls: List of tool call dictionaries from provider response.
            id_field: Field name for tool call ID.
            name_field: Field name for tool name.
            arguments_field: Field name for arguments (string or dict).
            function_wrapper: If set, tool name/args are nested under this key
                (e.g., OpenAI uses "function" wrapper).

        Returns:
            Tuple of (resolved_calls, unresolved_calls).

        Example:
            # OpenAI format
            tool_calls = [
                {
                    "id": "call_123",
                    "function": {
                        "name": "store_memory",
                        "arguments": '{"content": "hello"}'
                    }
                }
            ]
            resolved, unresolved = registry.parse_and_resolve(tool_calls)

            # Direct format (no function wrapper)
            tool_calls = [
                {"id": "1", "name": "calculator", "arguments": {"x": 1}}
            ]
            resolved, unresolved = registry.parse_and_resolve(
                tool_calls, function_wrapper=None
            )
        """
        resolved: list[ResolvedToolCall] = []
        unresolved: list[UnresolvedToolCall] = []

        for call in tool_calls:
            try:
                # Extract call ID
                call_id = str(call.get(id_field, ""))

                # Handle function wrapper (OpenAI style)
                if function_wrapper and function_wrapper in call:
                    inner = call[function_wrapper]
                    name = inner.get(name_field, "")
                    raw_args = inner.get(arguments_field, {})
                else:
                    name = call.get(name_field, "")
                    raw_args = call.get(arguments_field, {})

                # Parse arguments if string (JSON)
                if isinstance(raw_args, str):
                    try:
                        arguments = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError as e:
                        unresolved.append(UnresolvedToolCall(
                            call_id=call_id,
                            name=name,
                            arguments={},
                            error=f"Invalid JSON arguments: {e}",
                            raw=call,
                        ))
                        continue
                else:
                    arguments = raw_args if isinstance(raw_args, dict) else {}

                # Resolve tool by name (action_type)
                tool = self.get_tool(name)
                if tool is None:
                    unresolved.append(UnresolvedToolCall(
                        call_id=call_id,
                        name=name,
                        arguments=arguments,
                        error=f"No tool registered for action type: {name}",
                        raw=call,
                    ))
                else:
                    resolved.append(ResolvedToolCall(
                        tool=tool,
                        call_id=call_id,
                        name=name,
                        arguments=arguments,
                        raw=call,
                    ))

            except Exception as e:
                # Catch-all for malformed tool calls
                unresolved.append(UnresolvedToolCall(
                    call_id=str(call.get(id_field, "unknown")),
                    name=str(call.get(name_field, "unknown")),
                    arguments={},
                    error=f"Failed to parse tool call: {e}",
                    raw=call,
                ))

        return resolved, unresolved


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


def clear_tool_registry() -> None:
    """Clear all tools from the global registry.

    This is primarily useful for testing to ensure a clean state
    between tests. After calling this function, get_tool_registry()
    will return a fresh registry instance.

    Example:
        # In test setup or teardown
        clear_tool_registry()

        # Register fresh tools for this test
        register_tool(MyTestTool())
    """
    global _registry
    _registry = None


__all__ = [
    "ResolvedToolCall",
    "ToolRegistry",
    "UnresolvedToolCall",
    "clear_tool_registry",
    "get_tool_registry",
    "register_tool",
    "tool",
]
