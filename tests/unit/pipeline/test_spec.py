"""Unit tests for PipelineSpec dataclass."""

import pytest

from stageflow.core import StageOutput
from stageflow.pipeline.spec import PipelineSpec, PipelineValidationError, StageRunner
from stageflow.stages.context import PipelineContext


class MockStage:
    """Mock stage for testing."""

    async def execute(self, ctx: PipelineContext) -> StageOutput:
        return StageOutput.ok(data={"result": "success"})


class TestPipelineSpec:
    """Tests for PipelineSpec dataclass."""

    def test_create_valid_spec(self):
        """Test creating a valid PipelineSpec."""
        spec = PipelineSpec(
            name="test_stage",
            runner=MockStage,
            dependencies=("dep1", "dep2"),
            inputs=("input1",),
            outputs=("output1",),
        )
        assert spec.name == "test_stage"
        assert spec.dependencies == ("dep1", "dep2")
        assert spec.inputs == ("input1",)
        assert spec.outputs == ("output1",)
        assert spec.conditional is False
        assert spec.args == {}

    def test_create_spec_with_defaults(self):
        """Test creating PipelineSpec with default values."""
        spec = PipelineSpec(name="simple", runner=MockStage)
        assert spec.name == "simple"
        assert spec.dependencies == ()
        assert spec.inputs == ()
        assert spec.outputs == ()
        assert spec.conditional is False
        assert spec.args == {}

    def test_spec_rejects_empty_name(self):
        """Test that PipelineSpec rejects empty name."""
        with pytest.raises(ValueError, match="cannot be empty"):
            PipelineSpec(name="", runner=MockStage)

    def test_spec_rejects_whitespace_name(self):
        """Test that PipelineSpec rejects whitespace-only name."""
        with pytest.raises(ValueError, match="cannot be whitespace"):
            PipelineSpec(name="   ", runner=MockStage)

    def test_spec_rejects_self_dependency(self):
        """Test that PipelineSpec rejects self-dependency."""
        with pytest.raises(ValueError, match="cannot depend on itself"):
            PipelineSpec(
                name="my_stage",
                runner=MockStage,
                dependencies=("other", "my_stage"),
            )

    def test_spec_is_hashable(self):
        """Test that PipelineSpec is hashable for use in sets/dicts."""
        spec1 = PipelineSpec(name="stage1", runner=MockStage)
        spec2 = PipelineSpec(name="stage2", runner=MockStage)

        # Should be usable in a set
        spec_set = {spec1, spec2}
        assert len(spec_set) == 2

        # Should be usable as dict key
        spec_dict = {spec1: "value1", spec2: "value2"}
        assert spec_dict[spec1] == "value1"

    def test_spec_is_frozen(self):
        """Test that PipelineSpec is immutable (frozen)."""
        spec = PipelineSpec(name="frozen", runner=MockStage)
        with pytest.raises(AttributeError):
            spec.name = "changed"

    def test_spec_with_conditional(self):
        """Test creating a conditional PipelineSpec."""
        spec = PipelineSpec(
            name="conditional_stage",
            runner=MockStage,
            conditional=True,
        )
        assert spec.conditional is True

    def test_spec_with_args(self):
        """Test creating PipelineSpec with custom args."""
        spec = PipelineSpec(
            name="stage_with_args",
            runner=MockStage,
            args={"timeout": 30, "retries": 3},
        )
        assert spec.args == {"timeout": 30, "retries": 3}


class TestStageRunner:
    """Tests for StageRunner protocol."""

    def test_mock_stage_is_stage_runner(self):
        """Test that MockStage implements StageRunner protocol."""
        assert isinstance(MockStage(), StageRunner)

    def test_class_without_execute_is_not_runner(self):
        """Test that class without execute is not a StageRunner."""

        class NotAStage:
            pass

        assert not isinstance(NotAStage(), StageRunner)
