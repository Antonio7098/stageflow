"""Parallel enrichment pipeline - tests parallel execution."""

from stages.enrich import MemoryEnrichStage, ProfileEnrichStage
from stages.transform import SummarizeStage

from stageflow import Pipeline, StageKind


def create_parallel_pipeline() -> Pipeline:
    """Create a pipeline with parallel enrichment stages.

    DAG:
        [profile_enrich] ─┐
                          ├─> [summarize]
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
            name="summarize",
            runner=SummarizeStage,
            kind=StageKind.TRANSFORM,
            dependencies=("profile_enrich", "memory_enrich"),
        )
    )
