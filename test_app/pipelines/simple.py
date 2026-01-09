"""Simple echo pipeline - tests basic execution."""

from stageflow import Pipeline, StageKind

from stages.echo import EchoStage


def create_simple_pipeline() -> Pipeline:
    """Create a simple single-stage pipeline.
    
    DAG:
        [echo]
    """
    return Pipeline().with_stage(
        name="echo",
        runner=EchoStage,
        kind=StageKind.TRANSFORM,
    )
