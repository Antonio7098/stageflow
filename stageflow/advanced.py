"""Advanced Stageflow API for runtime customization and orchestration internals.

Use this module when you want a more explicit import surface for interceptors,
context internals, graph builders, and other advanced runtime controls.
"""

from stageflow.context import ContextSnapshot, Conversation, Enrichments, ExtensionBundle, RunIdentity
from stageflow.core import (
    Stage,
    StageContext,
    StageKind,
    StageOutput,
    StageReturn,
    StageStatus,
    stage_metadata,
)
from stageflow.observability import WideEventEmitter, emit_pipeline_wide_event, emit_stage_wide_event
from stageflow.pipeline import GuardRetryPolicy, GuardRetryStrategy, PipelineBuilder, PipelineResults, hash_retry_payload
from stageflow.pipeline.dag import (
    StageExecutionError,
    StageGraph,
    StageSpec,
    UnifiedStageExecutionError,
    UnifiedStageGraph,
)
from stageflow.pipeline.interceptors import (
    BaseInterceptor,
    ChildTrackerMetricsInterceptor,
    CircuitBreakerInterceptor,
    ErrorAction,
    InterceptorContext,
    InterceptorResult,
    LoggingInterceptor,
    MetricsInterceptor,
    TimeoutInterceptor,
    TracingInterceptor,
    get_default_interceptors,
    run_with_interceptors,
)
from stageflow.pipeline.interceptors_hardening import ContextSizeInterceptor, ImmutabilityInterceptor
from stageflow.pipeline.pipeline import Pipeline, UnifiedStageSpec, run_stage, stage
from stageflow.pipeline.spec import CycleDetectedError, PipelineValidationError
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageError, StageResult

__all__ = [
    "BaseInterceptor",
    "ChildTrackerMetricsInterceptor",
    "CircuitBreakerInterceptor",
    "ContextSizeInterceptor",
    "ContextSnapshot",
    "Conversation",
    "CycleDetectedError",
    "ErrorAction",
    "Enrichments",
    "ExtensionBundle",
    "get_default_interceptors",
    "GuardRetryPolicy",
    "GuardRetryStrategy",
    "hash_retry_payload",
    "ImmutabilityInterceptor",
    "InterceptorContext",
    "InterceptorResult",
    "LoggingInterceptor",
    "MetricsInterceptor",
    "Pipeline",
    "PipelineBuilder",
    "PipelineContext",
    "PipelineResults",
    "PipelineValidationError",
    "run_stage",
    "run_with_interceptors",
    "RunIdentity",
    "stage",
    "Stage",
    "stage_metadata",
    "StageContext",
    "StageError",
    "StageExecutionError",
    "StageGraph",
    "StageKind",
    "StageOutput",
    "StageReturn",
    "StageResult",
    "StageSpec",
    "StageStatus",
    "TimeoutInterceptor",
    "TracingInterceptor",
    "UnifiedStageExecutionError",
    "UnifiedStageGraph",
    "UnifiedStageSpec",
    "WideEventEmitter",
    "emit_pipeline_wide_event",
    "emit_stage_wide_event",
]