"""Tests for stageflow.tools.registry module.

Tests:
- ToolRegistry class
- get_tool_registry global function
- clear_tool_registry function
- register_tool function
- @tool decorator
"""

import pytest

from stageflow.tools import (
    BaseTool,
    ToolInput,
    ToolOutput,
    ToolRegistry,
    clear_tool_registry,
    get_tool_registry,
    register_tool,
    tool,
)


class DummyTool(BaseTool):
    """Dummy tool for testing."""

    name = "dummy"
    description = "A dummy tool for testing"
    action_type = "DUMMY_ACTION"

    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        return ToolOutput.ok(data={"result": "dummy"})


class AnotherTool(BaseTool):
    """Another dummy tool for testing."""

    name = "another"
    description = "Another tool"
    action_type = "ANOTHER_ACTION"

    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        return ToolOutput.ok(data={"result": "another"})


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    def test_empty_registry(self):
        """Test empty registry."""
        registry = ToolRegistry()
        assert registry.list_tools() == []

    def test_register_tool(self):
        """Test registering a tool instance."""
        registry = ToolRegistry()
        tool_instance = DummyTool()
        registry.register(tool_instance)
        assert registry.can_execute("DUMMY_ACTION")

    def test_get_tool(self):
        """Test getting a registered tool."""
        registry = ToolRegistry()
        tool_instance = DummyTool()
        registry.register(tool_instance)
        retrieved = registry.get_tool("DUMMY_ACTION")
        assert retrieved is tool_instance

    def test_get_missing_tool(self):
        """Test getting unregistered tool returns None."""
        registry = ToolRegistry()
        assert registry.get_tool("MISSING") is None

    def test_can_execute_true(self):
        """Test can_execute returns True for registered tool."""
        registry = ToolRegistry()
        registry.register(DummyTool())
        assert registry.can_execute("DUMMY_ACTION") is True

    def test_can_execute_false(self):
        """Test can_execute returns False for unregistered tool."""
        registry = ToolRegistry()
        assert registry.can_execute("MISSING") is False

    def test_list_tools(self):
        """Test list_tools returns all registered tools."""
        registry = ToolRegistry()
        tool1 = DummyTool()
        tool2 = AnotherTool()
        registry.register(tool1)
        registry.register(tool2)

        tools = registry.list_tools()
        assert len(tools) == 2
        assert tool1 in tools
        assert tool2 in tools

    def test_contains(self):
        """Test __contains__ method."""
        registry = ToolRegistry()
        registry.register(DummyTool())

        assert "DUMMY_ACTION" in registry
        assert "MISSING" not in registry

    def test_register_factory(self):
        """Test registering a factory function."""
        registry = ToolRegistry()
        registry.register_factory("FACTORY_ACTION", DummyTool)

        # Tool not created yet
        assert "FACTORY_ACTION" not in registry._tools
        # But can_execute should return True
        assert registry.can_execute("FACTORY_ACTION")
        # Getting tool should create it
        tool_instance = registry.get_tool("FACTORY_ACTION")
        assert tool_instance is not None
        assert isinstance(tool_instance, DummyTool)

    def test_factory_creates_on_first_get(self):
        """Test factory creates tool only on first get."""
        registry = ToolRegistry()
        call_count = {"count": 0}

        def counting_factory():
            call_count["count"] += 1
            return DummyTool()

        registry.register_factory("COUNTED_ACTION", counting_factory)

        # First get creates tool
        tool1 = registry.get_tool("COUNTED_ACTION")
        assert call_count["count"] == 1

        # Second get returns same tool
        tool2 = registry.get_tool("COUNTED_ACTION")
        assert call_count["count"] == 1
        assert tool1 is tool2


class TestGlobalRegistry:
    """Tests for global registry functions."""

    def setup_method(self):
        """Clear registry before each test."""
        clear_tool_registry()

    def teardown_method(self):
        """Clear registry after each test."""
        clear_tool_registry()

    def test_get_tool_registry_returns_registry(self):
        """Test get_tool_registry returns a ToolRegistry."""
        registry = get_tool_registry()
        assert isinstance(registry, ToolRegistry)

    def test_get_tool_registry_returns_same_instance(self):
        """Test get_tool_registry returns same instance."""
        registry1 = get_tool_registry()
        registry2 = get_tool_registry()
        assert registry1 is registry2

    def test_clear_tool_registry(self):
        """Test clear_tool_registry creates new instance."""
        registry1 = get_tool_registry()
        registry1.register(DummyTool())

        clear_tool_registry()

        registry2 = get_tool_registry()
        assert registry1 is not registry2
        assert registry2.list_tools() == []

    def test_clear_tool_registry_removes_tools(self):
        """Test clear_tool_registry removes all registered tools."""
        registry = get_tool_registry()
        registry.register(DummyTool())
        assert registry.can_execute("DUMMY_ACTION")

        clear_tool_registry()

        new_registry = get_tool_registry()
        assert not new_registry.can_execute("DUMMY_ACTION")


class TestRegisterToolFunction:
    """Tests for register_tool function."""

    def setup_method(self):
        """Clear registry before each test."""
        clear_tool_registry()

    def teardown_method(self):
        """Clear registry after each test."""
        clear_tool_registry()

    def test_register_tool_adds_to_global_registry(self):
        """Test register_tool adds to global registry."""
        tool_instance = DummyTool()
        register_tool(tool_instance)

        registry = get_tool_registry()
        assert registry.can_execute("DUMMY_ACTION")

    def test_register_tool_returns_none(self):
        """Test register_tool returns None."""
        result = register_tool(DummyTool())
        assert result is None


class TestToolDecorator:
    """Tests for @tool decorator."""

    def setup_method(self):
        """Clear registry before each test."""
        clear_tool_registry()

    def teardown_method(self):
        """Clear registry after each test."""
        clear_tool_registry()

    def test_tool_decorator_registers_factory(self):
        """Test @tool decorator registers a factory."""

        @tool("DECORATED_ACTION", name="decorated", description="A decorated tool")
        class DecoratedTool(BaseTool):
            name = "decorated"
            description = "A decorated tool"
            action_type = "DECORATED_ACTION"

            async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
                return ToolOutput.ok()

        # Tool should be registered via factory
        registry = get_tool_registry()
        assert registry.can_execute("DECORATED_ACTION")

    def test_tool_decorator_preserves_class(self):
        """Test @tool decorator returns the class unchanged."""

        @tool("TEST_ACTION")
        class TestTool(BaseTool):
            name = "test"
            description = "Test"
            action_type = "TEST_ACTION"

            async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
                return ToolOutput.ok()

        # Class should still be usable
        instance = TestTool()
        assert instance.action_type == "TEST_ACTION"

    def test_tool_decorator_stores_metadata(self):
        """Test @tool decorator stores metadata on class."""

        @tool("META_ACTION", name="meta_tool", description="Has metadata")
        class MetaTool(BaseTool):
            name = "meta"
            description = "Meta"
            action_type = "META_ACTION"

            async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
                return ToolOutput.ok()

        assert MetaTool._tool_action_type == "META_ACTION"
        assert MetaTool._tool_name == "meta_tool"
        assert MetaTool._tool_description == "Has metadata"
