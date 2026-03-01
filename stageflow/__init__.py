"""Stageflow - DAG-based pipeline orchestration framework.

This package provides a framework for building observable, composable
stage pipelines with parallel execution, cancellation, and interceptors.

Core Components:
- Stage: Protocol for pipeline stage implementations
- Pipeline: Fluent builder for composing stages into DAGs
- StageGraph: DAG executor with parallel execution
- Interceptors: Middleware for cross-cutting concerns
- EventSink: Protocol for event persistence

Stage Kinds:
- TRANSFORM: Data transformation stages (STT, TTS, LLM)
- ENRICH: Context enrichment stages (Profile, Memory)
- ROUTE: Routing decision stages (Router)
- GUARD: Guardrail/validation stages
- WORK: Side-effect stages (Persist, Assessment)
- AGENT: Agentic/coaching stages

Example:
    from stageflow import Pipeline, Stage, StageOutput, StageKind

    class MyStage:
        name = "my_stage"
        kind = StageKind.TRANSFORM

        async def execute(self, ctx):
            return StageOutput.ok(result="done")

    pipeline = Pipeline().with_stage("my", MyStage, StageKind.TRANSFORM)
    graph = pipeline.build()
    results = await graph.run(ctx)

Extension System:
Stageflow provides a generic extension system for application-specific data.
Use ContextSnapshot.extensions dict to store application data:

    snapshot = ContextSnapshot(
        ...
        extensions={"skills": {"active_skill_ids": ["python"]}}
    )

For type-safe extensions, use the ExtensionRegistry in stageflow.extensions.
"""

# Core stage types
# CLI and linting
from stageflow.cli.lint import (
    DependencyIssue,
    DependencyLintResult,
    IssueSeverity,
    lint_pipeline,
    lint_pipeline_file,
)
from stageflow.core import (
    PipelineTimer,
    Stage,
    StageArtifact,
    StageContext,
    StageEvent,
    StageKind,
    StageOutput,
    StageStatus,
    create_stage_context,
)

# Events
from stageflow.events import (
    BackpressureAwareEventSink,
    EventSink,
    LoggingEventSink,
    NoOpEventSink,
    clear_event_sink,
    get_event_sink,
    set_event_sink,
)

# Extensions
from stageflow.extensions import (
    ExtensionHelper,
    ExtensionRegistry,
    TypedExtension,
)

# Observability protocols
from stageflow.observability import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    PipelineRunLogger,
    ProviderCallLogger,
    WideEventEmitter,
    emit_pipeline_wide_event,
    emit_stage_wide_event,
    error_summary_to_stages_patch,
    error_summary_to_string,
    get_circuit_breaker,
    summarize_pipeline_error,
)
from stageflow.pipeline.builder import PipelineBuilder
from stageflow.pipeline.dag import (
    StageExecutionError,
    StageGraph,
    StageSpec,
    UnifiedStageExecutionError,
)

# Interceptors
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

# Pipeline types
from stageflow.pipeline.pipeline import (
    Pipeline,
    UnifiedStageSpec,
)
from stageflow.pipeline.registry import (
    PipelineRegistry,
    pipeline_registry,
)
from stageflow.pipeline.spec import (
    CycleDetectedError,
    PipelineValidationError,
)
from stageflow.pipeline.subpipeline import (
    ChildRunTracker,
    MaxDepthExceededError,
    SubpipelineResult,
    SubpipelineSpawner,
    get_child_tracker,
    get_subpipeline_spawner,
)

# Projector
from stageflow.projector.service import (
    WSMessageProjector,
    WSMetadata,
    WSOutboundMessage,
    WSStatusUpdatePayload,
    _coerce_uuid_str,
)
from stageflow.projector.service import (
    WSMessageProjector as ProjectorService,  # Backward compatibility
)

# Protocols
from stageflow.protocols import (
    ConfigProvider,
    CorrelationIds,
    RunStore,
)

# Context types
from stageflow.stages.context import (
    PipelineContext,
    extract_service,
)
from stageflow.stages.inputs import (
    StageInputs,
    create_stage_inputs,
)
from stageflow.stages.ports import (
    AudioPorts,
    CorePorts,
    LLMPorts,
    create_audio_ports,
    create_core_ports,
    create_llm_ports,
)
from stageflow.stages.result import (
    StageError,
    StageResult,
)

# Testing utilities (optional)
from stageflow.testing import (
    create_test_pipeline_context,
    create_test_snapshot,
    create_test_stage_context,
)

# Backward-compat aliases for historical API names.
LinearPipeline = Pipeline
create_test_context = create_test_stage_context

__all__ = [
    # Core stage types
    "Stage",
    "StageKind",
    "StageStatus",
    "StageOutput",
    "StageContext",
    "StageArtifact",
    "StageEvent",
    "StageError",
    "StageResult",
    # Context utilities
    "create_stage_context",
    # Timer
    "PipelineTimer",
    # Pipeline types
    "Pipeline",
    "PipelineBuilder",
    "LinearPipeline",
    "UnifiedStageSpec",
    # DAG types
    "StageExecutionError",
    "UnifiedStageExecutionError",
    "StageGraph",
    "StageSpec",
    # Registry
    "PipelineRegistry",
    "pipeline_registry",
    # Context types
    "PipelineContext",
    # Testing utilities
    "create_test_snapshot",
    "create_test_stage_context",
    "StageError",
    "extract_service",
    # Interceptors
    "BaseInterceptor",
    "InterceptorResult",
    "InterceptorContext",
    "ErrorAction",
    "LoggingInterceptor",
    "MetricsInterceptor",
    "ChildTrackerMetricsInterceptor",
    "TracingInterceptor",
    "CircuitBreakerInterceptor",
    "TimeoutInterceptor",
    "get_default_interceptors",
    "run_with_interceptors",
    # Events
    "EventSink",
    "NoOpEventSink",
    "LoggingEventSink",
    "BackpressureAwareEventSink",
    "get_event_sink",
    "set_event_sink",
    "clear_event_sink",
    # Protocols
    "RunStore",
    "ConfigProvider",
    "CorrelationIds",
    # Observability
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "PipelineRunLogger",
    "ProviderCallLogger",
    "summarize_pipeline_error",
    "error_summary_to_string",
    "error_summary_to_stages_patch",
    "get_circuit_breaker",
    # Extensions
    "ExtensionRegistry",
    "ExtensionHelper",
    "TypedExtension",
    # Stage inputs/ports
    "StageInputs",
    "create_stage_inputs",
    "CorePorts",
    "LLMPorts",
    "AudioPorts",
    "create_core_ports",
    "create_llm_ports",
    "create_audio_ports",
    # Pipeline validation
    "CycleDetectedError",
    "PipelineValidationError",
    # Subpipeline
    "SubpipelineSpawner",
    "SubpipelineResult",
    "ChildRunTracker",
    "MaxDepthExceededError",
    "get_child_tracker",
    "get_subpipeline_spawner",
    # CLI and linting
    "DependencyIssue",
    "DependencyLintResult",
    "IssueSeverity",
    "lint_pipeline",
    "lint_pipeline_file",
    # Projector
    "WSMessageProjector",
    "ProjectorService",
    "WSMetadata",
    "WSOutboundMessage",
    "WSStatusUpdatePayload",
    "_coerce_uuid_str",
    # Testing utilities
    "create_test_snapshot",
    "create_test_context",
    "create_test_pipeline_context",
    # Wide events
    "WideEventEmitter",
    "emit_stage_wide_event",
    "emit_pipeline_wide_event",
]
