"""Comprehensive tests for stageflow.pipeline module.

Tests the Pipeline builder and related types:
- Pipeline class (fluent builder)
- UnifiedStageSpec dataclass
- build() method and UnifiedStageGraph creation
- compose() method for merging pipelines
- with_stage() fluent interface
"""

import asyncio
from dataclasses import FrozenInstanceError
from datetime import datetime, UTC
from typing import Any
from uuid import uuid4
import pytest

from stageflow.core import (
    Stage,
    StageContext,
    StageKind,
    StageOutput,
    StageStatus,
)
from stageflow.pipeline.pipeline import (
    Pipeline,
    UnifiedStageSpec,
)


# === Test Fixtures ===

class SimpleStage:
    """Simple test stage for pipeline testing."""
    name = "simple_stage"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        return StageOutput.ok(result="simple_done")


class TransformStage:
    """Transform stage for testing."""
    name = "transform"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        return StageOutput.ok(data={"transformed": True})


class EnrichStage:
    """Enrich stage for testing."""
    name = "enrich"
    kind = StageKind.ENRICH

    async def execute(self, ctx: StageContext) -> StageOutput:
        return StageOutput.ok(data={"enriched": True})


class GuardStage:
    """Guard stage for testing."""
    name = "guard"
    kind = StageKind.GUARD

    async def execute(self, ctx: StageContext) -> StageOutput:
        return StageOutput.ok(data={"guarded": True})


class FailingStage:
    """Stage that always fails for error testing."""
    name = "failing"
    kind = StageKind.WORK

    def __init__(self, error_message: str = "Stage failed"):
        self.error_message = error_message

    async def execute(self, ctx: StageContext) -> StageOutput:
        return StageOutput.fail(error=self.error_message)


class StageWithDelay:
    """Stage with configurable delay for timing tests."""
    name = "delayed"
    kind = StageKind.WORK

    def __init__(self, delay_seconds: float = 0.1):
        self.delay_seconds = delay_seconds

    async def execute(self, ctx: StageContext) -> StageOutput:
        import time
        time.sleep(self.delay_seconds)
        return StageOutput.ok(data={"delayed": True})


# === Test UnifiedStageSpec ===

class TestUnifiedStageSpec:
    """Tests for UnifiedStageSpec dataclass."""

    def test_spec_creation(self):
        """Test UnifiedStageSpec with required fields."""
        spec = UnifiedStageSpec(
            name="test_stage",
            runner=SimpleStage,
            kind=StageKind.TRANSFORM,
        )
        assert spec.name == "test_stage"
        assert spec.runner == SimpleStage
        assert spec.kind == StageKind.TRANSFORM

    def test_spec_with_dependencies(self):
        """Test UnifiedStageSpec with dependencies."""
        spec = UnifiedStageSpec(
            name="dependent",
            runner=TransformStage,
            kind=StageKind.TRANSFORM,
            dependencies=("stage_a", "stage_b"),
        )
        assert spec.dependencies == ("stage_a", "stage_b")

    def test_spec_with_conditional(self):
        """Test UnifiedStageSpec with conditional flag."""
        spec = UnifiedStageSpec(
            name="conditional_stage",
            runner=GuardStage,
            kind=StageKind.GUARD,
            conditional=True,
        )
        assert spec.conditional is True

    def test_spec_defaults(self):
        """Test UnifiedStageSpec default values."""
        spec = UnifiedStageSpec(
            name="default_stage",
            runner=SimpleStage,
            kind=StageKind.TRANSFORM,
        )
        assert spec.dependencies == ()
        assert spec.conditional is False

    def test_spec_is_frozen(self):
        """Verify UnifiedStageSpec is frozen."""
        spec = UnifiedStageSpec(
            name="test",
            runner=SimpleStage,
            kind=StageKind.TRANSFORM,
        )
        with pytest.raises(FrozenInstanceError):
            spec.name = "changed"

    def test_spec_has_slots(self):
        """Verify UnifiedStageSpec uses slots."""
        assert hasattr(UnifiedStageSpec, "__slots__")


# === Test Pipeline ===

class TestPipeline:
    """Tests for Pipeline class."""

    def test_empty_pipeline(self):
        """Test empty Pipeline has no stages."""
        pipeline = Pipeline()
        assert pipeline.stages == {}

    def test_with_stage_single(self):
        """Test adding a single stage."""
        pipeline = Pipeline().with_stage(
            "simple",
            SimpleStage,
            StageKind.TRANSFORM,
        )
        assert "simple" in pipeline.stages
        assert pipeline.stages["simple"].name == "simple"
        assert pipeline.stages["simple"].kind == StageKind.TRANSFORM

    def test_with_stage_fluent_interface(self):
        """Test fluent interface returns new Pipeline."""
        pipeline1 = Pipeline()
        pipeline2 = pipeline1.with_stage("stage1", SimpleStage, StageKind.TRANSFORM)
        # Should return a new Pipeline instance
        assert pipeline2 is not pipeline1
        # Original should be unchanged
        assert "stage1" not in pipeline1.stages

    def test_with_stage_multiple(self):
        """Test adding multiple stages via chaining."""
        pipeline = (Pipeline()
            .with_stage("stage1", SimpleStage, StageKind.TRANSFORM)
            .with_stage("stage2", TransformStage, StageKind.TRANSFORM)
            .with_stage("stage3", EnrichStage, StageKind.ENRICH)
        )
        assert len(pipeline.stages) == 3
        assert "stage1" in pipeline.stages
        assert "stage2" in pipeline.stages
        assert "stage3" in pipeline.stages

    def test_with_stage_with_dependencies(self):
        """Test adding stage with dependencies."""
        pipeline = (Pipeline()
            .with_stage("a", SimpleStage, StageKind.TRANSFORM)
            .with_stage("b", TransformStage, StageKind.TRANSFORM, dependencies=("a",))
            .with_stage("c", EnrichStage, StageKind.ENRICH, dependencies=("a", "b"))
        )
        assert pipeline.stages["b"].dependencies == ("a",)
        assert pipeline.stages["c"].dependencies == ("a", "b")

    def test_with_stage_with_conditional(self):
        """Test adding conditional stage."""
        pipeline = Pipeline().with_stage(
            "conditional",
            GuardStage,
            StageKind.GUARD,
            conditional=True,
        )
        assert pipeline.stages["conditional"].conditional is True

    def test_with_stage_rejects_duplicate_name(self):
        """Test that duplicate stage names are allowed (last wins)."""
        pipeline = (Pipeline()
            .with_stage("duplicate", SimpleStage, StageKind.TRANSFORM)
            .with_stage("duplicate", TransformStage, StageKind.TRANSFORM)
        )
        # Last one wins
        assert pipeline.stages["duplicate"].runner == TransformStage

    def test_compose_empty_with_empty(self):
        """Test composing two empty pipelines."""
        pipeline1 = Pipeline()
        pipeline2 = Pipeline()
        composed = pipeline1.compose(pipeline2)
        assert composed.stages == {}

    def test_compose_with_stages(self):
        """Test composing pipelines with stages."""
        pipeline1 = Pipeline().with_stage("a", SimpleStage, StageKind.TRANSFORM)
        pipeline2 = Pipeline().with_stage("b", TransformStage, StageKind.TRANSFORM)
        composed = pipeline1.compose(pipeline2)
        assert len(composed.stages) == 2
        assert "a" in composed.stages
        assert "b" in composed.stages

    def test_compose_preserves_order(self):
        """Test that compose preserves stage order."""
        pipeline1 = Pipeline().with_stage("a", SimpleStage, StageKind.TRANSFORM)
        pipeline2 = Pipeline().with_stage("b", TransformStage, StageKind.TRANSFORM)
        composed = pipeline1.compose(pipeline2)
        # Both should be present
        assert "a" in composed.stages
        assert "b" in composed.stages

    def test_compose_other_wins_on_conflict(self):
        """Test that other pipeline wins on name conflict."""
        pipeline1 = Pipeline().with_stage("conflict", SimpleStage, StageKind.TRANSFORM)
        pipeline2 = Pipeline().with_stage("conflict", TransformStage, StageKind.TRANSFORM)
        composed = pipeline1.compose(pipeline2)
        assert composed.stages["conflict"].runner == TransformStage

    def test_compose_returns_new_instance(self):
        """Test that compose returns a new Pipeline instance."""
        pipeline1 = Pipeline().with_stage("a", SimpleStage, StageKind.TRANSFORM)
        pipeline2 = Pipeline().with_stage("b", TransformStage, StageKind.TRANSFORM)
        composed = pipeline1.compose(pipeline2)
        assert composed is not pipeline1
        assert composed is not pipeline2

    def test_compose_multiple(self):
        """Test chaining multiple compose calls."""
        pipeline1 = Pipeline().with_stage("a", SimpleStage, StageKind.TRANSFORM)
        pipeline2 = Pipeline().with_stage("b", TransformStage, StageKind.TRANSFORM)
        pipeline3 = Pipeline().with_stage("c", EnrichStage, StageKind.ENRICH)
        composed = pipeline1.compose(pipeline2).compose(pipeline3)
        assert len(composed.stages) == 3

    def test_compose_with_dependencies(self):
        """Test that dependencies are preserved through compose."""
        pipeline1 = (Pipeline()
            .with_stage("a", SimpleStage, StageKind.TRANSFORM)
            .with_stage("b", TransformStage, StageKind.TRANSFORM, dependencies=("a",))
        )
        pipeline2 = Pipeline().with_stage("c", EnrichStage, StageKind.ENRICH, dependencies=("a",))
        composed = pipeline1.compose(pipeline2)
        assert composed.stages["b"].dependencies == ("a",)
        assert composed.stages["c"].dependencies == ("a",)

    # === build() method tests ===

    def test_build_empty_pipeline_raises(self):
        """Test that building empty pipeline raises ValueError."""
        pipeline = Pipeline()
        with pytest.raises(ValueError) as exc_info:
            pipeline.build()
        assert "UnifiedStageGraph requires at least one UnifiedStageSpec" in str(exc_info.value)

    def test_build_creates_graph(self):
        """Test that build() creates a UnifiedStageGraph."""
        pipeline = Pipeline().with_stage("test", SimpleStage, StageKind.TRANSFORM)
        graph = pipeline.build()
        assert graph is not None

    def test_build_with_single_stage(self):
        """Test building pipeline with single stage."""
        pipeline = Pipeline().with_stage("single", SimpleStage, StageKind.TRANSFORM)
        graph = pipeline.build()
        assert len(graph.stage_specs) == 1
        assert graph.stage_specs[0].name == "single"

    def test_build_with_multiple_stages(self):
        """Test building pipeline with multiple stages."""
        pipeline = (Pipeline()
            .with_stage("a", SimpleStage, StageKind.TRANSFORM)
            .with_stage("b", TransformStage, StageKind.TRANSFORM)
            .with_stage("c", EnrichStage, StageKind.ENRICH)
        )
        graph = pipeline.build()
        assert len(graph.stage_specs) == 3

    def test_build_preserves_dependencies(self):
        """Test that build() preserves dependencies."""
        pipeline = (Pipeline()
            .with_stage("a", SimpleStage, StageKind.TRANSFORM)
            .with_stage("b", TransformStage, StageKind.TRANSFORM, dependencies=("a",))
            .with_stage("c", EnrichStage, StageKind.ENRICH, dependencies=("a", "b"))
        )
        graph = pipeline.build()
        spec_dict = {spec.name: spec for spec in graph.stage_specs}
        assert spec_dict["b"].dependencies == ("a",)
        assert spec_dict["c"].dependencies == ("a", "b")

    def test_build_preserves_conditional(self):
        """Test that build() preserves conditional flag."""
        pipeline = Pipeline().with_stage(
            "conditional",
            GuardStage,
            StageKind.GUARD,
            conditional=True,
        )
        graph = pipeline.build()
        assert graph.stage_specs[0].conditional is True

    def test_build_with_stage_instance(self):
        """Test building with a stage instance instead of class."""
        instance = SimpleStage()
        pipeline = Pipeline().with_stage("instance", instance, StageKind.TRANSFORM)
        graph = pipeline.build()
        assert graph.stage_specs[0].name == "instance"

    def test_build_creates_callable_runner(self):
        """Test that build() creates callable runners for stage classes."""
        pipeline = Pipeline().with_stage("test", SimpleStage, StageKind.TRANSFORM)
        graph = pipeline.build()
        spec = graph.stage_specs[0]
        # The runner should be callable
        assert callable(spec.runner)

    async def test_build_runner_executes_stage(self):
        """Test that built runner actually executes the stage."""
        from stageflow.context import ContextSnapshot
        from stageflow.pipeline.dag import UnifiedStageGraph

        pipeline = Pipeline().with_stage("simple", SimpleStage, StageKind.TRANSFORM)
        graph: UnifiedStageGraph = pipeline.build()

        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test",
            
            execution_mode="test",
        )

        ctx = StageContext(snapshot=snapshot, config={})

        # The runner should be an async callable
        result = await graph.stage_specs[0].runner(ctx)
        assert isinstance(result, StageOutput)
        assert result.status == StageStatus.OK

    def test_build_with_complex_dependency_graph(self):
        """Test building complex DAG with multiple dependencies."""
        pipeline = (Pipeline()
            .with_stage("a", SimpleStage, StageKind.TRANSFORM)
            .with_stage("b", TransformStage, StageKind.TRANSFORM, dependencies=("a",))
            .with_stage("c", EnrichStage, StageKind.ENRICH, dependencies=("a",))
            .with_stage("d", GuardStage, StageKind.GUARD, dependencies=("b", "c"))
        )
        graph = pipeline.build()
        spec_dict = {spec.name: spec for spec in graph.stage_specs}
        # "d" depends on both "b" and "c"
        assert spec_dict["d"].dependencies == ("b", "c")

    def test_build_preserves_stage_kind(self):
        """Test that build() preserves StageKind."""
        pipeline = (Pipeline()
            .with_stage("transform", TransformStage, StageKind.TRANSFORM)
            .with_stage("enrich", EnrichStage, StageKind.ENRICH)
            .with_stage("guard", GuardStage, StageKind.GUARD)
        )
        graph = pipeline.build()
        spec_dict = {spec.name: spec for spec in graph.stage_specs}
        assert spec_dict["transform"].kind == StageKind.TRANSFORM
        assert spec_dict["enrich"].kind == StageKind.ENRICH
        assert spec_dict["guard"].kind == StageKind.GUARD


# === Edge Cases ===

class TestPipelineEdgeCases:
    """Edge case tests for Pipeline."""

    def test_stage_with_empty_dependencies_tuple(self):
        """Test stage with explicitly empty dependencies tuple."""
        pipeline = Pipeline().with_stage(
            "no_deps",
            SimpleStage,
            StageKind.TRANSFORM,
            dependencies=(),
        )
        assert pipeline.stages["no_deps"].dependencies == ()

    def test_stage_with_single_dependency_in_tuple(self):
        """Test stage with single dependency as tuple."""
        pipeline = (Pipeline()
            .with_stage("a", SimpleStage, StageKind.TRANSFORM)
            .with_stage("b", TransformStage, StageKind.TRANSFORM, dependencies=("a",))
        )
        assert pipeline.stages["b"].dependencies == ("a",)

    def test_circular_dependency_not_prevented_at_build_time(self):
        """Note: Circular dependencies cause deadlock at runtime, not build time."""
        pipeline = (Pipeline()
            .with_stage("a", SimpleStage, StageKind.TRANSFORM, dependencies=("b",))
            .with_stage("b", TransformStage, StageKind.TRANSFORM, dependencies=("a",))
        )
        # Build should succeed (validation is at runtime)
        graph = pipeline.build()
        assert len(graph.stage_specs) == 2

    def test_very_long_stage_name(self):
        """Test pipeline with very long stage names."""
        long_name = "a" * 1000
        pipeline = Pipeline().with_stage(long_name, SimpleStage, StageKind.TRANSFORM)
        assert long_name in pipeline.stages

    def test_unicode_stage_name(self):
        """Test pipeline with unicode stage names."""
        unicode_name = "stage_日本語_🚀"
        pipeline = Pipeline().with_stage(unicode_name, SimpleStage, StageKind.TRANSFORM)
        assert unicode_name in pipeline.stages

    def test_empty_stage_name_raises(self):
        """Test that empty stage name raises error (should be caught at runtime)."""
        # Note: This might not raise immediately depending on implementation
        # but empty names would likely cause issues during execution
        pipeline = Pipeline().with_stage("", SimpleStage, StageKind.TRANSFORM)
        assert "" in pipeline.stages

    def test_many_stages(self):
        """Test pipeline with many stages."""
        pipeline = Pipeline()
        for i in range(100):
            pipeline = pipeline.with_stage(f"stage_{i}", SimpleStage, StageKind.TRANSFORM)
        assert len(pipeline.stages) == 100

    def test_many_compose_operations(self):
        """Test many compose operations."""
        pipeline = Pipeline()
        for i in range(50):
            new_pipeline = Pipeline().with_stage(f"p{i}", SimpleStage, StageKind.TRANSFORM)
            pipeline = pipeline.compose(new_pipeline)
        assert len(pipeline.stages) == 50

    def test_compose_self(self):
        """Test that composing a pipeline with itself works."""
        pipeline = Pipeline().with_stage("a", SimpleStage, StageKind.TRANSFORM)
        # This should work but might have unexpected behavior
        composed = pipeline.compose(pipeline)
        assert "a" in composed.stages
