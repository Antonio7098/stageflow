"""Stageflow pipeline module - pipeline types and registry."""

from stageflow.core.stages import Stage
from stageflow.pipeline.dag import StageExecutionError, StageGraph, StageSpec
from stageflow.pipeline.pipeline import Pipeline, UnifiedStageSpec
from stageflow.pipeline.registry import PipelineRegistry, pipeline_registry
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageError, StageResult

__all__ = [
    "Pipeline",
    "UnifiedStageSpec",
    "PipelineRegistry",
    "pipeline_registry",
    "PipelineContext",
    "Stage",
    "StageError",
    "StageResult",
    "StageGraph",
    "StageSpec",
    "StageExecutionError",
]
