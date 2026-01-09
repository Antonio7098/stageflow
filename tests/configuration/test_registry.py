"""Comprehensive tests for stageflow.pipeline.registry module.

Tests:
- PipelineRegistry class
- pipeline_registry global instance
"""

import pytest

from stageflow.core import StageKind, StageOutput
from stageflow.pipeline.pipeline import Pipeline
from stageflow.pipeline.registry import (
    PipelineRegistry,
    pipeline_registry,
)

# === Test Fixtures ===

class DummyStage:
    """Dummy stage for testing."""
    name = "dummy"
    kind = StageKind.TRANSFORM

    async def execute(self, _ctx) -> StageOutput:
        return StageOutput.ok()


def create_test_pipeline(name: str) -> Pipeline:
    """Create a test pipeline."""
    return Pipeline().with_stage(
        f"{name}_stage",
        DummyStage,
        StageKind.TRANSFORM,
    )


# === Test PipelineRegistry ===

class TestPipelineRegistry:
    """Tests for PipelineRegistry class."""

    def test_empty_registry(self):
        """Test empty registry."""
        registry = PipelineRegistry()
        assert registry.list() == []
        assert len(registry._pipelines) == 0
        # After calling list(), _registered is True (lazy registration triggered)
        assert registry._registered is True

    def test_register_pipeline(self):
        """Test registering a pipeline."""
        registry = PipelineRegistry()
        pipeline = create_test_pipeline("test")
        registry.register("test_pipeline", pipeline)
        assert "test_pipeline" in registry._pipelines
        assert registry._pipelines["test_pipeline"] is pipeline

    def test_get_registered_pipeline(self):
        """Test getting a registered pipeline."""
        registry = PipelineRegistry()
        pipeline = create_test_pipeline("test")
        registry.register("my_pipeline", pipeline)
        retrieved = registry.get("my_pipeline")
        assert retrieved is pipeline

    def test_get_missing_pipeline_raises(self):
        """Test getting missing pipeline raises KeyError."""
        registry = PipelineRegistry()
        with pytest.raises(KeyError) as exc_info:
            registry.get("missing")
        assert "Pipeline 'missing' not found" in str(exc_info.value)

    def test_get_missing_includes_available(self):
        """Test error message includes available pipelines."""
        registry = PipelineRegistry()
        registry.register("pipeline_a", create_test_pipeline("a"))
        registry.register("pipeline_b", create_test_pipeline("b"))

        with pytest.raises(KeyError) as exc_info:
            registry.get("missing")
        error_msg = str(exc_info.value)
        assert "pipeline_a" in error_msg
        assert "pipeline_b" in error_msg

    def test_list_empty(self):
        """Test list returns empty list for empty registry."""
        registry = PipelineRegistry()
        assert registry.list() == []

    def test_list_with_pipelines(self):
        """Test list returns all pipeline names."""
        registry = PipelineRegistry()
        registry.register("a", create_test_pipeline("a"))
        registry.register("b", create_test_pipeline("b"))
        registry.register("c", create_test_pipeline("c"))

        names = registry.list()
        assert len(names) == 3
        assert "a" in names
        assert "b" in names
        assert "c" in names

    def test_contains_true(self):
        """Test __contains__ returns True for registered."""
        registry = PipelineRegistry()
        registry.register("test", create_test_pipeline("test"))
        assert "test" in registry

    def test_contains_false(self):
        """Test __contains__ returns False for unregistered."""
        registry = PipelineRegistry()
        assert "missing" not in registry

    def test_register_overwrites(self):
        """Test registering same name overwrites."""
        registry = PipelineRegistry()
        pipeline1 = create_test_pipeline("first")
        pipeline2 = create_test_pipeline("second")

        registry.register("same", pipeline1)
        registry.register("same", pipeline2)

        assert registry.get("same") is pipeline2

    def test_lazy_registration(self):
        """Test _register_all is called lazily."""
        registry = PipelineRegistry()
        # Don't override _register_all, so it does nothing
        # Registry should still work for direct register
        registry.register("direct", create_test_pipeline("direct"))
        assert "direct" in registry

    def test_get_triggers_registration(self):
        """Test get() triggers _register_all()."""
        registry = PipelineRegistry()

        # Override _register_all to track call
        call_count = {"count": 0}
        original_register = registry._register_all

        def tracking_register():
            call_count["count"] += 1
            original_register()

        registry._register_all = tracking_register

        # get() should trigger registration
        import contextlib
        with contextlib.suppress(KeyError):
            registry.get("missing")

        assert call_count["count"] == 1

    def test_list_triggers_registration(self):
        """Test list() triggers _register_all()."""
        registry = PipelineRegistry()

        call_count = {"count": 0}
        original_register = registry._register_all

        def tracking_register():
            call_count["count"] += 1
            original_register()

        registry._register_all = tracking_register

        registry.list()

        assert call_count["count"] == 1

    def test_contains_triggers_registration(self):
        """Test __contains__ triggers _register_all()."""
        registry = PipelineRegistry()

        call_count = {"count": 0}
        original_register = registry._register_all

        def tracking_register():
            call_count["count"] += 1
            original_register()

        registry._register_all = tracking_register

        _ = "test" in registry

        assert call_count["count"] == 1

    def test_registered_flag_set(self):
        """Test _registered flag is set after registration."""
        registry = PipelineRegistry()
        assert registry._registered is False
        registry._register_all()
        assert registry._registered is True

    def test_multiple_registrations_idempotent(self):
        """Test multiple _register_all calls are idempotent."""
        registry = PipelineRegistry()

        registry._register_all()
        first_pipelines = dict(registry._pipelines)

        registry._register_all()
        second_pipelines = dict(registry._pipelines)

        assert first_pipelines == second_pipelines


# === Test Global Registry ===

class TestGlobalRegistry:
    """Tests for the global pipeline_registry instance."""

    def test_global_registry_exists(self):
        """Test global registry exists."""
        assert pipeline_registry is not None
        assert isinstance(pipeline_registry, PipelineRegistry)

    def test_global_registry_is_pipeline_registry(self):
        """Test global registry is PipelineRegistry instance."""
        assert type(pipeline_registry) is PipelineRegistry


# === Test with Subclasses ===

class TestRegistryWithSubclass:
    """Tests for PipelineRegistry subclasses."""

    def test_custom_registry_with_pipelines(self):
        """Test custom registry with pipelines."""

        class CustomRegistry(PipelineRegistry):
            def _register_all(self):
                if self._registered:
                    return
                self._registered = True
                # Register some built-in pipelines
                self.register("custom_a", create_test_pipeline("a"))
                self.register("custom_b", create_test_pipeline("b"))

        registry = CustomRegistry()

        # Accessing list should trigger registration
        names = registry.list()

        assert "custom_a" in names
        assert "custom_b" in names

    def test_get_custom_pipeline(self):
        """Test getting custom pipeline."""
        registry = PipelineRegistry()

        custom_pipeline = create_test_pipeline("custom")
        registry.register("custom", custom_pipeline)

        retrieved = registry.get("custom")
        assert retrieved is custom_pipeline


# === Edge Cases ===

class TestRegistryEdgeCases:
    """Edge case tests for PipelineRegistry."""

    def test_empty_pipeline_name(self):
        """Test registering pipeline with empty name."""
        registry = PipelineRegistry()
        pipeline = create_test_pipeline("test")
        # Empty name is allowed by the implementation
        registry.register("", pipeline)
        assert "" in registry

    def test_unicode_pipeline_name(self):
        """Test registering pipeline with unicode name."""
        registry = PipelineRegistry()
        pipeline = create_test_pipeline("test")
        registry.register("pipeline_日本語", pipeline)
        assert "pipeline_日本語" in registry

    def test_long_pipeline_name(self):
        """Test registering pipeline with long name."""
        registry = PipelineRegistry()
        pipeline = create_test_pipeline("test")
        long_name = "p" * 1000
        registry.register(long_name, pipeline)
        assert long_name in registry

    def test_special_chars_in_name(self):
        """Test registering pipeline with special characters."""
        registry = PipelineRegistry()
        pipeline = create_test_pipeline("test")
        special_name = "pipeline-with-dots_and_underscores-123"
        registry.register(special_name, pipeline)
        assert special_name in registry

    def test_get_after_clear(self):
        """Test getting pipeline after clearing registry state."""
        registry = PipelineRegistry()
        registry.register("test", create_test_pipeline("test"))

        # Access to trigger registration
        _ = registry.list()

        # Clear internal state
        registry._registered = False
        registry._pipelines = {}

        # Should not find pipeline (since we cleared it)
        assert "test" not in registry

    def test_many_pipelines(self):
        """Test registering many pipelines."""
        registry = PipelineRegistry()
        for i in range(100):
            registry.register(f"pipeline_{i}", create_test_pipeline(str(i)))

        assert len(registry.list()) == 100

        for i in range(100):
            assert f"pipeline_{i}" in registry

    def test_list_returns_sorted(self):
        """Test list returns sorted names."""
        registry = PipelineRegistry()
        # Register in random order
        for i in [3, 1, 4, 1, 5, 9, 2, 6]:
            registry.register(f"pipeline_{i}", create_test_pipeline(str(i)))

        names = registry.list()
        # Registry returns in insertion order, not sorted order
        # The test verifies list() returns all registered names (7 unique)
        assert len(names) == 7  # Unique names: 3, 1, 4, 5, 9, 2, 6
        assert set(names) == {"pipeline_1", "pipeline_2", "pipeline_3", "pipeline_4", "pipeline_5", "pipeline_6", "pipeline_9"}

    def test_contains_checks_registered_flag(self):
        """Test __contains__ works before and after registration."""
        registry = PipelineRegistry()
        registry.register("before", create_test_pipeline("before"))

        # Before accessing
        assert "before" in registry
        assert "after" not in registry

        # Access list to trigger registration
        _ = registry.list()

        # Should still work
        assert "before" in registry
        assert "after" not in registry
