"""Stageflow pipeline module - pipeline types and registry."""

from stageflow.core import Stage
from stageflow.pipeline.builder import PipelineBuilder
from stageflow.pipeline.dag import StageExecutionError, StageGraph, StageSpec
from stageflow.pipeline.guard_retry import (
    GuardRetryPolicy,
    GuardRetryStrategy,
    hash_retry_payload,
)
from stageflow.pipeline.pipeline import Pipeline, UnifiedStageSpec
from stageflow.pipeline.registry import PipelineRegistry, pipeline_registry
from stageflow.pipeline.spec import (
    CycleDetectedError,
    PipelineSpec,
    PipelineValidationError,
    StageRunner,
)
from stageflow.pipeline.subpipeline import (
    DEFAULT_MAX_SUBPIPELINE_DEPTH,
    ChildRunTracker,
    MaxDepthExceededError,
    PipelineCanceledEvent,
    PipelineChildCompletedEvent,
    PipelineChildFailedEvent,
    PipelineSpawnedChildEvent,
    SubpipelineResult,
    SubpipelineSpawner,
    clear_child_tracker,
    clear_subpipeline_spawner,
    get_child_tracker,
    get_subpipeline_spawner,
    set_child_tracker,
    set_subpipeline_spawner,
)
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageError, StageResult

__all__ = [
    "Pipeline",
    "PipelineBuilder",
    "PipelineSpec",
    "PipelineValidationError",
    "CycleDetectedError",
    "PipelineRegistry",
    "pipeline_registry",
    "PipelineContext",
    "Stage",
    "StageError",
    "StageResult",
    "StageGraph",
    "StageRunner",
    "StageSpec",
    "StageExecutionError",
    "UnifiedStageSpec",
    "GuardRetryPolicy",
    "GuardRetryStrategy",
    "hash_retry_payload",
    # Subpipeline support
    "DEFAULT_MAX_SUBPIPELINE_DEPTH",
    "MaxDepthExceededError",
    "SubpipelineResult",
    "SubpipelineSpawner",
    "ChildRunTracker",
    "PipelineSpawnedChildEvent",
    "PipelineChildCompletedEvent",
    "PipelineChildFailedEvent",
    "PipelineCanceledEvent",
    "get_child_tracker",
    "set_child_tracker",
    "clear_child_tracker",
    "get_subpipeline_spawner",
    "set_subpipeline_spawner",
    "clear_subpipeline_spawner",
]
