"""Pipeline builder for code-defined DAG composition.

This module provides the Pipeline dataclass and fluent builder API
for composing stages into executable DAGs. Replaces JSON-based
pipeline configuration with type-safe Python code.

Usage:
    pipeline = Pipeline()
        .with_stage("router", RouterStage, StageKind.ROUTE)
        .with_stage("llm", LlmStreamStage, StageKind.TRANSFORM, dependencies=("router",))
graph = pipeline.build()
    result = await orchestrator.run(graph, snapshot)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from stageflow.observability.wide_events import WideEventEmitter
from stageflow.pipeline.validation import (
    ensure_compatible_stage_specs,
    ensure_non_empty,
    topologically_sorted_stage_names,
    validate_stage_dependencies,
)

if TYPE_CHECKING:
    from stageflow.core import Stage, StageKind
    from stageflow.pipeline.guard_retry import GuardRetryStrategy
    from stageflow.pipeline.interceptors import BaseInterceptor


@dataclass(frozen=True, slots=True)
class UnifiedStageSpec:
    """Specification for a stage in the pipeline DAG.

    Combines the stage class/instance with metadata needed
    for DAG execution (kind, dependencies, conditional flag).
    """

    name: str
    runner: type[Stage] | Stage
    kind: StageKind
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    conditional: bool = False
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class Pipeline:
    """Builder for composing stages into a pipeline DAG.

    Provides a fluent API for adding stages, composing pipelines,
    and     building executable UnifiedStageGraph instances.

    Attributes:
        stages: Mapping of stage name -> UnifiedStageSpec
    """

    name: str = "pipeline"
    stages: dict[str, UnifiedStageSpec] = field(default_factory=dict)

    def _validated_stages(self) -> dict[str, UnifiedStageSpec]:
        """Return stages after dependency/cycle validation."""
        validate_stage_dependencies(self.stages)
        return self.stages

    def with_stage(
        self,
        name: str,
        runner: type[Stage] | Stage,
        kind: StageKind,
        dependencies: tuple[str, ...] | None = None,
        conditional: bool = False,
        config: dict[str, Any] | None = None,
    ) -> Pipeline:
        """Add a stage to this pipeline (fluent builder).

        Args:
            name: Unique stage name within the pipeline
            runner: Stage class or instance to execute
            kind: StageKind categorization
            dependencies: Names of stages that must complete first
            conditional: If True, stage may be skipped based on context
            config: Optional kwargs passed to the stage constructor (class runners only)

            Returns:
            Self for method chaining
        """
        if config and not isinstance(runner, type):
            raise ValueError("config can only be used with stage classes")

        spec = UnifiedStageSpec(
            name=name,
            runner=runner,
            kind=kind,
            dependencies=dependencies or (),
            conditional=conditional,
            config=dict(config or {}),
        )
        # Create new Pipeline instance to maintain immutability
        new_pipeline = Pipeline(name=self.name, stages=dict(self.stages))
        new_pipeline.stages[name] = spec
        return new_pipeline

    def compose(self, other: Pipeline) -> Pipeline:
        """Merge stages and dependencies from another pipeline.

        Stages from the other pipeline are added to this pipeline.
        If stage names conflict, the definitions must be compatible.

        Args:
            other: Another Pipeline instance to merge

            Returns:
            New Pipeline with merged stages
        """
        merged_stages = dict(self.stages)
        for name, spec in other.stages.items():
            if name in merged_stages:
                ensure_compatible_stage_specs(
                    name=name,
                    existing=merged_stages[name],
                    incoming=spec,
                    attrs=("runner", "kind", "dependencies", "conditional", "config"),
                )
                continue
            merged_stages[name] = spec
        composed_name = self.name if self.name == other.name else f"{self.name}+{other.name}"
        return Pipeline(name=composed_name, stages=merged_stages)

    def get_stage(self, name: str) -> UnifiedStageSpec | None:
        """Get a stage specification by name."""
        return self.stages.get(name)

    def has_stage(self, name: str) -> bool:
        """Check whether a stage exists in the pipeline."""
        return name in self.stages

    def stage_names(self) -> list[str]:
        """Return stage names in topological order."""
        return topologically_sorted_stage_names(self.stages)

    def build(
        self,
        *,
        interceptors: list[BaseInterceptor] | None = None,
        guard_retry_strategy: GuardRetryStrategy | None = None,
        emit_stage_wide_events: bool = False,
        emit_pipeline_wide_event: bool = False,
        wide_event_emitter: WideEventEmitter | None = None,
    ) -> UnifiedStageGraph:
        """Generate executable DAG for the orchestrator.

        Creates a UnifiedStageGraph from the stage specifications.
        Validates that at least one stage exists and dependencies
        are resolvable.

        Args:
            interceptors: Optional interceptor stack. If omitted, defaults
                from get_default_interceptors() are used.
            guard_retry_strategy: Optional guard retry policy strategy.

        Returns:
            UnifiedStageGraph ready for orchestration

        Raises:
            PipelineValidationError: If pipeline is empty or dependencies are invalid
        """
        ensure_non_empty(self.stages, message="Cannot build empty pipeline")
        validated_stages = self._validated_stages()

        # Convert stage classes to callables for UnifiedStageGraph
        specs_for_graph = []
        for spec in validated_stages.values():
            if isinstance(spec.runner, type):
                # It's a stage class, create a callable wrapper
                stage_class = spec.runner
                stage_config = dict(spec.config)

                async def runner_wrapper(ctx, stage_cls=stage_class, stage_cfg=stage_config):
                    stage_instance = stage_cls(**stage_cfg) if stage_cfg else stage_cls()
                    return await stage_instance.execute(ctx)

                callable_runner = runner_wrapper
            elif hasattr(spec.runner, 'execute'):
                # It's a stage instance with an execute method
                stage_instance = spec.runner

                async def runner_wrapper(ctx, stage=stage_instance):
                    return await stage.execute(ctx)

                callable_runner = runner_wrapper
            else:
                # It's already a callable
                callable_runner = spec.runner

            # Create a new spec with the callable runner
            from stageflow.pipeline.dag import UnifiedStageSpec as GraphUnifiedStageSpec

            graph_spec = GraphUnifiedStageSpec(
                name=spec.name,
                runner=callable_runner,  # type: ignore
                kind=spec.kind,
                dependencies=spec.dependencies,
                conditional=spec.conditional,
            )
            specs_for_graph.append(graph_spec)

        # Import here to avoid circular imports
        from stageflow.pipeline.dag import UnifiedStageGraph

        return UnifiedStageGraph(  # type: ignore
            specs=specs_for_graph,
            pipeline_name=self.name,
            interceptors=interceptors,
            guard_retry_strategy=guard_retry_strategy,
            wide_event_emitter=wide_event_emitter,
            emit_stage_wide_events=emit_stage_wide_events,
            emit_pipeline_wide_event=emit_pipeline_wide_event,
        )


# Forward declaration for type hints
class UnifiedStageGraph(Protocol):
    """Protocol for the executable DAG produced by Pipeline.build().

    The actual implementation lives in stageflow.pipeline.dag
    but we use a protocol here to avoid circular imports.
    """

    stage_specs: list[UnifiedStageSpec]


__all__ = [
    "Pipeline",
    "UnifiedStageSpec",
    "UnifiedStageGraph",
]
