"""Transform chain pipeline - tests linear dependencies."""

from stages.transform import ReverseStage, SummarizeStage, UppercaseStage

from stageflow import Pipeline, StageKind


def create_transform_pipeline() -> Pipeline:
    """Create a linear chain of transform stages.

    DAG:
        [uppercase] -> [reverse] -> [summarize]
    """
    return (
        Pipeline()
        .with_stage(
            name="uppercase",
            runner=UppercaseStage,
            kind=StageKind.TRANSFORM,
        )
        .with_stage(
            name="reverse",
            runner=ReverseStage,
            kind=StageKind.TRANSFORM,
            dependencies=("uppercase",),
        )
        .with_stage(
            name="summarize",
            runner=SummarizeStage,
            kind=StageKind.TRANSFORM,
            dependencies=("reverse",),
        )
    )
