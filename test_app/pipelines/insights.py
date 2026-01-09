"""Pipelines focused on contextual insights and follow-up generation."""

from stageflow import Pipeline, StageKind

from stages.enrich import ProfileEnrichStage, MemoryEnrichStage
from stages.transform import InsightsStage, FollowUpStage
from stages.guard import InputGuardStage, OutputGuardStage


def create_insights_pipeline() -> Pipeline:
    """Pipeline that aggregates enrichment data into insights and follow ups.

    DAG:
        [profile_enrich] ─┐
                          ├─> [insights] -> [follow_up]
        [memory_enrich] ──┘
    """
    return (
        Pipeline()
        .with_stage(
            name="profile_enrich",
            runner=ProfileEnrichStage(),
            kind=StageKind.ENRICH,
        )
        .with_stage(
            name="memory_enrich",
            runner=MemoryEnrichStage(),
            kind=StageKind.ENRICH,
        )
        .with_stage(
            name="insights",
            runner=InsightsStage,
            kind=StageKind.TRANSFORM,
            dependencies=("profile_enrich", "memory_enrich"),
        )
        .with_stage(
            name="follow_up",
            runner=FollowUpStage(max_questions=4),
            kind=StageKind.WORK,
            dependencies=("insights",),
        )
    )


def create_guarded_insights_pipeline() -> Pipeline:
    """Guarded variant that validates input/output around insights generation.

    DAG:
        [input_guard] -> [profile_enrich] ─┐
                           [memory_enrich] ├─> [insights] -> [follow_up] -> [output_guard]
    """
    return (
        Pipeline()
        .with_stage(
            name="input_guard",
            runner=InputGuardStage(),
            kind=StageKind.GUARD,
        )
        .with_stage(
            name="profile_enrich",
            runner=ProfileEnrichStage(),
            kind=StageKind.ENRICH,
            dependencies=("input_guard",),
        )
        .with_stage(
            name="memory_enrich",
            runner=MemoryEnrichStage(),
            kind=StageKind.ENRICH,
            dependencies=("input_guard",),
        )
        .with_stage(
            name="insights",
            runner=InsightsStage,
            kind=StageKind.TRANSFORM,
            dependencies=("profile_enrich", "memory_enrich"),
        )
        .with_stage(
            name="follow_up",
            runner=FollowUpStage(max_questions=3),
            kind=StageKind.WORK,
            dependencies=("insights",),
        )
        .with_stage(
            name="output_guard",
            runner=OutputGuardStage(),
            kind=StageKind.GUARD,
            dependencies=("follow_up",),
        )
    )


__all__ = [
    "create_insights_pipeline",
    "create_guarded_insights_pipeline",
]
