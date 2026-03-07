"""Curated Stageflow API for the common happy path.

Import from this module when you want the smallest practical public surface for
application code. Prefer `Pipeline.run(...)` as the canonical execution verb;
`Pipeline.invoke(...)` remains available as a convenience alias for scripts.
Advanced orchestration types remain available from `stageflow.advanced`, the
root package, and submodules.
"""

from stageflow.core import (
    Stage,
    StageArtifact,
    StageContext,
    StageEvent,
    StageKind,
    StageOutput,
    StageReturn,
    StageStatus,
    stage_metadata,
)
from stageflow.pipeline.pipeline import Pipeline, run_stage, stage
from stageflow.pipeline.results import PipelineResults
from stageflow.stages.context import PipelineContext

__all__ = [
    "Pipeline",
    "PipelineContext",
    "PipelineResults",
    "Stage",
    "StageArtifact",
    "StageContext",
    "StageEvent",
    "StageKind",
    "StageOutput",
    "StageReturn",
    "StageStatus",
    "stage",
    "run_stage",
    "stage_metadata",
]
