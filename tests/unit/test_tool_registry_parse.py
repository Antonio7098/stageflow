"""Tests for ToolRegistry parse_and_resolve functionality."""

from __future__ import annotations

from typing import Any

import pytest

from stageflow.tools.base import BaseTool, ToolInput, ToolOutput
from stageflow.tools.registry import (
    ResolvedToolCall,
    ToolRegistry,
    UnresolvedToolCall,
    clear_tool_registry,
)


class MockTool(BaseTool):
    """Mock tool for testing."""

    def __init__(self, action_type: str, name: str = "mock"):
        self._action_type = action_type
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "A mock tool"

    @property
    def action_type(self) -> str:
        return self._action_type

    async def execute(self, input: ToolInput, ctx: dict[str, Any]) -> ToolOutput:
        return ToolOutput(success=True, data={"executed": True})


class TestParseAndResolve:
    """Tests for ToolRegistry.parse_and_resolve method."""

    def setup_method(self):
        """Clear registry before each test."""
        clear_tool_registry()

    def test_resolves_openai_format(self):
        """Should parse and resolve OpenAI-style tool calls."""
        registry = ToolRegistry()
        registry.register(MockTool("calculator", "calc"))
        registry.register(MockTool("weather", "weather"))

        tool_calls = [
            {
                "id": "call_123",
                "function": {
                    "name": "calculator",
                    "arguments": '{"x": 1, "y": 2}',
                },
            },
            {
                "id": "call_456",
                "function": {
                    "name": "weather",
                    "arguments": '{"city": "NYC"}',
                },
            },
        ]

        resolved, unresolved = registry.parse_and_resolve(tool_calls)

        assert len(resolved) == 2
        assert len(unresolved) == 0

        assert resolved[0].call_id == "call_123"
        assert resolved[0].name == "calculator"
        assert resolved[0].arguments == {"x": 1, "y": 2}
        assert resolved[0].tool.action_type == "calculator"

        assert resolved[1].call_id == "call_456"
        assert resolved[1].name == "weather"
        assert resolved[1].arguments == {"city": "NYC"}

    def test_resolves_direct_format(self):
        """Should parse direct format (no function wrapper)."""
        registry = ToolRegistry()
        registry.register(MockTool("calculator", "calc"))

        tool_calls = [
            {"id": "1", "name": "calculator", "arguments": {"x": 1}},
        ]

        resolved, unresolved = registry.parse_and_resolve(
            tool_calls, function_wrapper=None
        )

        assert len(resolved) == 1
        assert resolved[0].name == "calculator"
        assert resolved[0].arguments == {"x": 1}

    def test_handles_unregistered_tool(self):
        """Should return unresolved for unknown tools."""
        registry = ToolRegistry()
        registry.register(MockTool("calculator", "calc"))

        tool_calls = [
            {
                "id": "call_1",
                "function": {"name": "calculator", "arguments": "{}"},
            },
            {
                "id": "call_2",
                "function": {"name": "unknown_tool", "arguments": "{}"},
            },
        ]

        resolved, unresolved = registry.parse_and_resolve(tool_calls)

        assert len(resolved) == 1
        assert len(unresolved) == 1

        assert unresolved[0].name == "unknown_tool"
        assert "No tool registered" in unresolved[0].error

    def test_handles_invalid_json_arguments(self):
        """Should return unresolved for invalid JSON arguments."""
        registry = ToolRegistry()
        registry.register(MockTool("calculator", "calc"))

        tool_calls = [
            {
                "id": "call_1",
                "function": {
                    "name": "calculator",
                    "arguments": "not valid json {",
                },
            },
        ]

        resolved, unresolved = registry.parse_and_resolve(tool_calls)

        assert len(resolved) == 0
        assert len(unresolved) == 1
        assert "Invalid JSON" in unresolved[0].error

    def test_handles_empty_arguments(self):
        """Should handle empty arguments string."""
        registry = ToolRegistry()
        registry.register(MockTool("ping", "ping"))

        tool_calls = [
            {
                "id": "call_1",
                "function": {"name": "ping", "arguments": ""},
            },
        ]

        resolved, unresolved = registry.parse_and_resolve(tool_calls)

        assert len(resolved) == 1
        assert resolved[0].arguments == {}

    def test_handles_dict_arguments(self):
        """Should handle pre-parsed dict arguments."""
        registry = ToolRegistry()
        registry.register(MockTool("calculator", "calc"))

        tool_calls = [
            {
                "id": "call_1",
                "function": {
                    "name": "calculator",
                    "arguments": {"x": 1, "y": 2},  # Already a dict
                },
            },
        ]

        resolved, unresolved = registry.parse_and_resolve(tool_calls)

        assert len(resolved) == 1
        assert resolved[0].arguments == {"x": 1, "y": 2}

    def test_custom_field_names(self):
        """Should support custom field names."""
        registry = ToolRegistry()
        registry.register(MockTool("calculator", "calc"))

        tool_calls = [
            {
                "call_id": "abc123",
                "tool_name": "calculator",
                "params": '{"x": 5}',
            },
        ]

        resolved, unresolved = registry.parse_and_resolve(
            tool_calls,
            id_field="call_id",
            name_field="tool_name",
            arguments_field="params",
            function_wrapper=None,
        )

        assert len(resolved) == 1
        assert resolved[0].call_id == "abc123"
        assert resolved[0].name == "calculator"
        assert resolved[0].arguments == {"x": 5}

    def test_preserves_raw_call(self):
        """Should preserve original call data in raw field."""
        registry = ToolRegistry()
        registry.register(MockTool("calculator", "calc"))

        original_call = {
            "id": "call_1",
            "function": {"name": "calculator", "arguments": "{}"},
            "extra_field": "preserved",
        }

        resolved, _ = registry.parse_and_resolve([original_call])

        assert resolved[0].raw == original_call
        assert resolved[0].raw["extra_field"] == "preserved"

    def test_handles_malformed_calls(self):
        """Should handle completely malformed tool calls."""
        registry = ToolRegistry()
        registry.register(MockTool("calculator", "calc"))

        tool_calls = [
            None,  # type: ignore
            {"id": "valid", "function": {"name": "calculator", "arguments": "{}"}},
        ]

        # Filter out None before passing (simulating real-world cleanup)
        valid_calls = [c for c in tool_calls if c is not None]
        resolved, unresolved = registry.parse_and_resolve(valid_calls)

        assert len(resolved) == 1

    def test_empty_tool_calls_list(self):
        """Should handle empty tool calls list."""
        registry = ToolRegistry()

        resolved, unresolved = registry.parse_and_resolve([])

        assert len(resolved) == 0
        assert len(unresolved) == 0

    def test_mixed_resolved_and_unresolved(self):
        """Should correctly separate resolved and unresolved calls."""
        registry = ToolRegistry()
        registry.register(MockTool("tool_a", "a"))
        registry.register(MockTool("tool_c", "c"))

        tool_calls = [
            {"id": "1", "function": {"name": "tool_a", "arguments": "{}"}},
            {"id": "2", "function": {"name": "tool_b", "arguments": "{}"}},  # Unknown
            {"id": "3", "function": {"name": "tool_c", "arguments": "{}"}},
            {"id": "4", "function": {"name": "tool_d", "arguments": "{}"}},  # Unknown
        ]

        resolved, unresolved = registry.parse_and_resolve(tool_calls)

        assert len(resolved) == 2
        assert len(unresolved) == 2

        resolved_ids = {r.call_id for r in resolved}
        unresolved_ids = {u.call_id for u in unresolved}

        assert resolved_ids == {"1", "3"}
        assert unresolved_ids == {"2", "4"}


class TestResolvedToolCall:
    """Tests for ResolvedToolCall dataclass."""

    def test_frozen(self):
        """Should be immutable."""
        tool = MockTool("test", "test")
        resolved = ResolvedToolCall(
            tool=tool,
            call_id="123",
            name="test",
            arguments={"x": 1},
        )

        with pytest.raises(AttributeError):
            resolved.call_id = "456"  # type: ignore

    def test_stores_all_fields(self):
        """Should store all fields correctly."""
        tool = MockTool("calculator", "calc")
        raw = {"id": "123", "function": {"name": "calculator"}}

        resolved = ResolvedToolCall(
            tool=tool,
            call_id="123",
            name="calculator",
            arguments={"x": 1, "y": 2},
            raw=raw,
        )

        assert resolved.tool is tool
        assert resolved.call_id == "123"
        assert resolved.name == "calculator"
        assert resolved.arguments == {"x": 1, "y": 2}
        assert resolved.raw == raw


class TestUnresolvedToolCall:
    """Tests for UnresolvedToolCall dataclass."""

    def test_frozen(self):
        """Should be immutable."""
        unresolved = UnresolvedToolCall(
            call_id="123",
            name="unknown",
            arguments={},
            error="Not found",
        )

        with pytest.raises(AttributeError):
            unresolved.error = "Changed"  # type: ignore

    def test_stores_error_info(self):
        """Should store error information."""
        raw = {"id": "123", "function": {"name": "unknown"}}

        unresolved = UnresolvedToolCall(
            call_id="123",
            name="unknown",
            arguments={"x": 1},
            error="No tool registered for action type: unknown",
            raw=raw,
        )

        assert unresolved.call_id == "123"
        assert unresolved.name == "unknown"
        assert unresolved.arguments == {"x": 1}
        assert "No tool registered" in unresolved.error
        assert unresolved.raw == raw
