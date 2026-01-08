"""Stageflow stages module - exports stage types."""

from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageError, StageResult

__all__ = [
    "StageError",
    "PipelineContext",
    "StageResult",
]
