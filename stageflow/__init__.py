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
    error_summary_to_stages_patch,
    error_summary_to_string,
    get_circuit_breaker,
    summarize_pipeline_error,
)
from stageflow.pipeline.dag import (
    StageExecutionError,
    StageGraph,
    StageSpec,
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

__all__ = [
    # Core stage types
    "Stage",
    "StageKind",
    "StageStatus",
    "StageOutput",
    "StageContext",
    "StageArtifact",
    "StageEvent",
    "PipelineTimer",
    "create_stage_context",
    # Pipeline types
    "Pipeline",
    "UnifiedStageSpec",
    "PipelineRegistry",
    "pipeline_registry",
    "StageSpec",
    "StageGraph",
    "StageExecutionError",
    # Context types
    "PipelineContext",
    "StageResult",
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
]
