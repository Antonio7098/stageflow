"""Unit tests for PipelineBuilder class."""

import pytest

from stageflow.core.stages import StageOutput
from stageflow.pipeline.builder import PipelineBuilder
from stageflow.pipeline.spec import PipelineSpec, PipelineValidationError
from stageflow.stages.context import PipelineContext


class MockStageA:
    """Mock stage A for testing."""

    async def execute(self, ctx: PipelineContext) -> StageOutput:
        return StageOutput.ok(data={"stage": "A"})


class MockStageB:
    """Mock stage B for testing."""

    async def execute(self, ctx: PipelineContext) -> StageOutput:
        return StageOutput.ok(data={"stage": "B"})


class MockStageC:
    """Mock stage C for testing."""

    async def execute(self, ctx: PipelineContext) -> StageOutput:
        return StageOutput.ok(data={"stage": "C"})


class TestPipelineBuilder:
    """Tests for PipelineBuilder class."""

    def test_create_empty_pipeline(self):
        """Test creating an empty PipelineBuilder."""
        pipeline = PipelineBuilder(name="empty")
        assert pipeline.name == "empty"
        assert len(pipeline.stages) == 0

    def test_add_stage(self):
        """Test adding a stage to the pipeline."""
        pipeline = PipelineBuilder(name="test").with_stage(
            name="stage_a",
            runner=MockStageA,
        )
        assert "stage_a" in pipeline.stages
        assert pipeline.stages["stage_a"].name == "stage_a"

    def test_add_stage_with_dependencies(self):
        """Test adding a stage with dependencies."""
        pipeline = (
            PipelineBuilder(name="test")
            .with_stage(name="stage_a", runner=MockStageA)
            .with_stage(
                name="stage_b",
                runner=MockStageB,
                dependencies=("stage_a",),
            )
        )
        assert pipeline.stages["stage_b"].dependencies == ("stage_a",)

    def test_add_stage_is_immutable(self):
        """Test that with_stage returns a new pipeline (immutable)."""
        pipeline1 = PipelineBuilder(name="test")
        pipeline2 = pipeline1.with_stage(name="stage_a", runner=MockStageA)

        assert len(pipeline1.stages) == 0
        assert len(pipeline2.stages) == 1

    def test_rejects_missing_dependency(self):
        """Test that pipeline rejects missing dependency."""
        with pytest.raises(PipelineValidationError, match="does not exist"):
            PipelineBuilder(
                name="test",
                stages={
                    "stage_b": PipelineSpec(
                        name="stage_b",
                        runner=MockStageB,
                        dependencies=("nonexistent",),
                    )
                },
            )

    def test_rejects_simple_cycle(self):
        """Test that pipeline rejects simple cycle (A→B→A)."""
        with pytest.raises(PipelineValidationError, match="cycle"):
            PipelineBuilder(
                name="test",
                stages={
                    "stage_a": PipelineSpec(
                        name="stage_a",
                        runner=MockStageA,
                        dependencies=("stage_b",),
                    ),
                    "stage_b": PipelineSpec(
                        name="stage_b",
                        runner=MockStageB,
                        dependencies=("stage_a",),
                    ),
                },
            )

    def test_rejects_complex_cycle(self):
        """Test that pipeline rejects complex cycle (A→B→C→A)."""
        with pytest.raises(PipelineValidationError, match="cycle"):
            PipelineBuilder(
                name="test",
                stages={
                    "stage_a": PipelineSpec(
                        name="stage_a",
                        runner=MockStageA,
                        dependencies=("stage_c",),
                    ),
                    "stage_b": PipelineSpec(
                        name="stage_b",
                        runner=MockStageB,
                        dependencies=("stage_a",),
                    ),
                    "stage_c": PipelineSpec(
                        name="stage_c",
                        runner=MockStageC,
                        dependencies=("stage_b",),
                    ),
                },
            )

    def test_compose_merges_stages(self):
        """Test that compose() merges stages from both pipelines."""
        pipeline1 = PipelineBuilder(name="p1").with_stage(
            name="stage_a", runner=MockStageA
        )
        pipeline2 = PipelineBuilder(name="p2").with_stage(
            name="stage_b", runner=MockStageB
        )

        composed = pipeline1.compose(pipeline2)

        assert "stage_a" in composed.stages
        assert "stage_b" in composed.stages
        assert composed.name == "p1+p2"

    def test_compose_rejects_conflicting_stages(self):
        """Test that compose() rejects conflicting stage specs."""
        pipeline1 = PipelineBuilder(name="p1").with_stage(
            name="stage_a", runner=MockStageA
        )
        pipeline2 = PipelineBuilder(name="p2").with_stage(
            name="stage_a",
            runner=MockStageB,  # Different runner
        )

        with pytest.raises(PipelineValidationError, match="different specs"):
            pipeline1.compose(pipeline2)

    def test_compose_allows_identical_stages(self):
        """Test that compose() allows identical stage specs."""
        pipeline1 = PipelineBuilder(name="p1").with_stage(
            name="stage_a", runner=MockStageA
        )
        pipeline2 = PipelineBuilder(name="p2").with_stage(
            name="stage_a", runner=MockStageA
        )

        # Should not raise
        composed = pipeline1.compose(pipeline2)
        assert "stage_a" in composed.stages

    def test_build_returns_stage_graph(self):
        """Test that build() returns a valid StageGraph."""
        pipeline = (
            PipelineBuilder(name="test")
            .with_stage(name="stage_a", runner=MockStageA)
            .with_stage(
                name="stage_b",
                runner=MockStageB,
                dependencies=("stage_a",),
            )
        )

        graph = pipeline.build()

        # StageGraph should have the specs
        assert len(graph.stage_specs) == 2

    def test_build_empty_pipeline_raises(self):
        """Test that build() raises on empty pipeline."""
        pipeline = PipelineBuilder(name="empty")

        with pytest.raises(ValueError, match="empty"):
            pipeline.build()

    def test_get_stage(self):
        """Test get_stage() returns correct spec."""
        pipeline = PipelineBuilder(name="test").with_stage(
            name="stage_a", runner=MockStageA
        )

        spec = pipeline.get_stage("stage_a")
        assert spec is not None
        assert spec.name == "stage_a"

        missing = pipeline.get_stage("nonexistent")
        assert missing is None

    def test_has_stage(self):
        """Test has_stage() returns correct boolean."""
        pipeline = PipelineBuilder(name="test").with_stage(
            name="stage_a", runner=MockStageA
        )

        assert pipeline.has_stage("stage_a") is True
        assert pipeline.has_stage("nonexistent") is False

    def test_stage_names_topological_order(self):
        """Test stage_names() returns stages in topological order."""
        # Build pipeline with stages added in order that satisfies dependencies
        pipeline = (
            PipelineBuilder(name="test")
            .with_stage(name="stage_a", runner=MockStageA)
            .with_stage(name="stage_b", runner=MockStageB, dependencies=("stage_a",))
            .with_stage(name="stage_c", runner=MockStageC, dependencies=("stage_b",))
        )

        names = pipeline.stage_names()

        # stage_a must come before stage_b, stage_b before stage_c
        assert names.index("stage_a") < names.index("stage_b")
        assert names.index("stage_b") < names.index("stage_c")

    def test_repr(self):
        """Test __repr__ provides useful debugging info."""
        pipeline = PipelineBuilder(name="test").with_stage(
            name="stage_a", runner=MockStageA
        )

        repr_str = repr(pipeline)
        assert "test" in repr_str
        assert "stage_a" in repr_str
