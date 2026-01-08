"""Unit tests for Pipeline builder."""

import pytest

from stageflow import Pipeline, StageKind, StageOutput


class MockStage:
    """Mock stage for testing."""
    
    name = "mock_stage"
    kind = StageKind.TRANSFORM
    
    async def execute(self, ctx):
        return StageOutput.ok(result="mock")


class TestPipeline:
    """Tests for Pipeline builder."""

    def test_create_empty_pipeline(self):
        """Pipeline() creates empty pipeline."""
        pipeline = Pipeline()
        
        assert len(pipeline.stages) == 0

    def test_with_stage_adds_stage(self):
        """with_stage() adds a stage to the pipeline."""
        pipeline = Pipeline().with_stage(
            "test",
            MockStage,
            StageKind.TRANSFORM,
        )
        
        assert "test" in pipeline.stages
        assert pipeline.stages["test"].name == "test"
        assert pipeline.stages["test"].kind == StageKind.TRANSFORM

    def test_with_stage_is_immutable(self):
        """with_stage() returns new Pipeline, doesn't modify original."""
        pipeline1 = Pipeline()
        pipeline2 = pipeline1.with_stage("test", MockStage, StageKind.TRANSFORM)
        
        assert len(pipeline1.stages) == 0
        assert len(pipeline2.stages) == 1

    def test_with_stage_with_dependencies(self):
        """with_stage() accepts dependencies tuple."""
        pipeline = (
            Pipeline()
            .with_stage("first", MockStage, StageKind.TRANSFORM)
            .with_stage("second", MockStage, StageKind.TRANSFORM, dependencies=("first",))
        )
        
        assert pipeline.stages["second"].dependencies == ("first",)

    def test_compose_merges_pipelines(self):
        """compose() merges two pipelines."""
        pipeline1 = Pipeline().with_stage("stage1", MockStage, StageKind.TRANSFORM)
        pipeline2 = Pipeline().with_stage("stage2", MockStage, StageKind.WORK)
        
        composed = pipeline1.compose(pipeline2)
        
        assert "stage1" in composed.stages
        assert "stage2" in composed.stages

    def test_build_raises_on_empty_pipeline(self):
        """build() raises ValueError on empty pipeline."""
        pipeline = Pipeline()
        
        with pytest.raises(ValueError, match="at least one"):
            pipeline.build()
