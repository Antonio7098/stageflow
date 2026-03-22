"""Pipeline builder for code-defined DAG composition.

This module provides the Pipeline dataclass and fluent builder API
for composing stages into executable DAGs. Replaces JSON-based
pipeline configuration with type-safe Python code.

Usage:
    pipeline = Pipeline()
        .with_stage("router", RouterStage, StageKind.ROUTE)
        .with_stage("llm", LlmStreamStage, StageKind.TRANSFORM, dependencies=("router",))
    result = await pipeline.run(input_text="hello")
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from stageflow.observability.wide_events import WideEventEmitter
from stageflow.pipeline.results import PipelineResults
from stageflow.pipeline.validation import (
    ensure_compatible_stage_specs,
    ensure_non_empty,
    topologically_sorted_stage_names,
    validate_stage_dependencies,
)

if TYPE_CHECKING:
    from stageflow.core import Stage, StageContext, StageKind, StageOutput
    from stageflow.pipeline.guard_retry import GuardRetryStrategy
    from stageflow.pipeline.interceptors import BaseInterceptor
    from stageflow.stages.context import PipelineContext


def _normalize_dependencies(
    dependencies: tuple[str, ...] | list[str] | None = None,
    *,
    after: str | Sequence[str] | None = None,
) -> tuple[str, ...]:
    if dependencies is not None and after is not None:
        raise ValueError("Use either dependencies=... or after=..., not both")

    if after is None:
        return tuple(dependencies or ())
    if isinstance(after, str):
        return (after,)
    return tuple(after)


def _infer_stage_kind(runner: Any) -> StageKind:
    from stageflow.core import StageKind

    candidate = getattr(runner, "kind", None)
    if isinstance(candidate, StageKind):
        return candidate
    if isinstance(candidate, str):
        try:
            return StageKind(candidate)
        except ValueError as exc:
            raise ValueError(f"Unsupported stage kind value on runner: {candidate!r}") from exc

    raise ValueError(
        "kind is required unless the runner exposes a valid `.kind` attribute"
    )


def _resolve_stage_kind(runner: Any, kind: StageKind | str | None) -> StageKind:
    if kind is None:
        return _infer_stage_kind(runner)
    return _infer_stage_kind(type("_KindHolder", (), {"kind": kind}))


def stage(
    name: str,
    runner: type[Stage] | Stage,
    kind: StageKind | str | None = None,
    dependencies: tuple[str, ...] | list[str] | None = None,
    *,
    after: str | Sequence[str] | None = None,
    conditional: bool = False,
    config: dict[str, Any] | None = None,
) -> UnifiedStageSpec:
    """Create a declarative stage spec for `Pipeline.with_stages(...)`.

    This keeps pipeline dependencies explicit while reducing repeated boilerplate
    in pipeline definitions.

    Use `after=` for simple tutorial-style chains. Use `dependencies=` when you
    want to emphasize explicit DAG edges or declare multiple upstream stages.
    """
    if config and not isinstance(runner, type):
        raise ValueError("config can only be used with stage classes")

    resolved_kind = _resolve_stage_kind(runner, kind)
    resolved_dependencies = _normalize_dependencies(dependencies, after=after)
    return UnifiedStageSpec(
        name=name,
        runner=runner,
        kind=resolved_kind,
        dependencies=resolved_dependencies,
        conditional=conditional,
        config=dict(config or {}),
    )


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

    @classmethod
    def from_stages(cls, *specs: UnifiedStageSpec, name: str = "pipeline") -> Pipeline:
        """Construct a pipeline from declarative stage specs."""
        return cls(name=name).with_stages(*specs)

    def _validated_stages(self) -> dict[str, UnifiedStageSpec]:
        """Return stages after dependency/cycle validation."""
        validate_stage_dependencies(self.stages)
        return self.stages

    def with_stage(
        self,
        name: str,
        runner: type[Stage] | Stage,
        kind: StageKind | str | None = None,
        dependencies: tuple[str, ...] | list[str] | None = None,
        *,
        after: str | Sequence[str] | None = None,
        conditional: bool = False,
        config: dict[str, Any] | None = None,
    ) -> Pipeline:
        """Add a stage to this pipeline (fluent builder).

        Args:
            name: Unique stage name within the pipeline
            runner: Stage class or instance to execute
            kind: StageKind categorization. If omitted, inferred from runner.kind.
            dependencies: Names of stages that must complete first
            after: Readable alias for dependencies when expressing DAG edges inline
            conditional: If True, stage may be skipped based on context
            config: Optional kwargs passed to the stage constructor (class runners only)

        Returns:
            Self for method chaining
        """
        spec = stage(
            name=name,
            runner=runner,
            kind=kind,
            dependencies=dependencies,
            after=after,
            conditional=conditional,
            config=config,
        )
        # Create new Pipeline instance to maintain immutability
        new_pipeline = Pipeline(name=self.name, stages=dict(self.stages))
        new_pipeline.stages[name] = spec
        return new_pipeline

    def with_stages(self, *specs: UnifiedStageSpec) -> Pipeline:
        """Add multiple declarative stage specs to this pipeline."""
        result = self
        for spec in specs:
            result = result.with_stage(
                spec.name,
                spec.runner,
                spec.kind,
                spec.dependencies,
                conditional=spec.conditional,
                config=spec.config,
            )
        return result

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

    async def run(
        self,
        ctx: PipelineContext | StageContext | None = None,
        /,
        *,
        interceptors: list[BaseInterceptor] | None = None,
        guard_retry_strategy: GuardRetryStrategy | None = None,
        emit_stage_wide_events: bool = False,
        emit_pipeline_wide_event: bool = False,
        wide_event_emitter: WideEventEmitter | None = None,
        **context_kwargs: Any,
    ) -> PipelineResults:
        """Build and execute this pipeline in one step.

        This is the canonical convenience entrypoint for application code.
        It preserves the same execution behavior as ``build().run(...)`` while
        avoiding an extra local variable when you do not need to retain the graph.

        Args:
            ctx: Root execution context. ``PipelineContext`` is the recommended
                caller-facing type.
            **context_kwargs: Convenience keyword arguments forwarded to
                ``PipelineContext.create(...)`` when ``ctx`` is omitted.

        Returns:
            PipelineResults mapping stage name to ``StageOutput``.
        """
        if ctx is not None and context_kwargs:
            raise ValueError("Pass either ctx or PipelineContext keyword fields, not both")

        if ctx is None:
            from stageflow.stages.context import PipelineContext

            if "pipeline_name" not in context_kwargs:
                context_kwargs["pipeline_name"] = self.name
            ctx = PipelineContext.create(**context_kwargs)

        graph = self.build(
            interceptors=interceptors,
            guard_retry_strategy=guard_retry_strategy,
            emit_stage_wide_events=emit_stage_wide_events,
            emit_pipeline_wide_event=emit_pipeline_wide_event,
            wide_event_emitter=wide_event_emitter,
        )
        return PipelineResults(await graph.run(ctx))

    async def invoke(
        self,
        input_text_or_ctx: str | PipelineContext | StageContext | None = None,
        /,
        *,
        interceptors: list[BaseInterceptor] | None = None,
        guard_retry_strategy: GuardRetryStrategy | None = None,
        emit_stage_wide_events: bool = False,
        emit_pipeline_wide_event: bool = False,
        wide_event_emitter: WideEventEmitter | None = None,
        **context_kwargs: Any,
    ) -> PipelineResults:
        """Small alias for `run(...)` with optional positional input text.

        Prefer `run(...)` in reusable application code and docs. `invoke(...)`
        exists for scripts and other call sites where a positional input string
        reads more naturally.
        """
        from stageflow.core import StageContext
        from stageflow.stages.context import PipelineContext

        if isinstance(input_text_or_ctx, (PipelineContext, StageContext)):
            if "input_text" in context_kwargs:
                raise ValueError("Do not pass input_text when invoke() receives a context object")
            return await self.run(
                input_text_or_ctx,
                interceptors=interceptors,
                guard_retry_strategy=guard_retry_strategy,
                emit_stage_wide_events=emit_stage_wide_events,
                emit_pipeline_wide_event=emit_pipeline_wide_event,
                wide_event_emitter=wide_event_emitter,
            )

        if input_text_or_ctx is not None:
            if "input_text" in context_kwargs:
                raise ValueError("input_text provided twice")
            context_kwargs["input_text"] = input_text_or_ctx

        return await self.run(
            None,
            interceptors=interceptors,
            guard_retry_strategy=guard_retry_strategy,
            emit_stage_wide_events=emit_stage_wide_events,
            emit_pipeline_wide_event=emit_pipeline_wide_event,
            wide_event_emitter=wide_event_emitter,
            **context_kwargs,
        )


async def run_stage(
    name: str,
    runner: type[Stage] | Stage,
    kind: StageKind | str | None = None,
    /,
    *,
    interceptors: list[BaseInterceptor] | None = None,
    guard_retry_strategy: GuardRetryStrategy | None = None,
    emit_stage_wide_events: bool = False,
    emit_pipeline_wide_event: bool = False,
    wide_event_emitter: WideEventEmitter | None = None,
    conditional: bool = False,
    config: dict[str, Any] | None = None,
    **context_kwargs: Any,
) -> StageOutput:
    """Execute a single stage through the unified pipeline runtime."""
    pipeline_name = str(context_kwargs.get("pipeline_name") or f"{name}_pipeline")
    pipeline = Pipeline(name=pipeline_name).with_stage(
        name,
        runner,
        kind,
        conditional=conditional,
        config=config,
    )
    results = await pipeline.run(
        None,
        interceptors=interceptors,
        guard_retry_strategy=guard_retry_strategy,
        emit_stage_wide_events=emit_stage_wide_events,
        emit_pipeline_wide_event=emit_pipeline_wide_event,
        wide_event_emitter=wide_event_emitter,
        **context_kwargs,
    )
    return results.require(name)


# Forward declaration for type hints
class UnifiedStageGraph(Protocol):
    """Protocol for the executable DAG produced by Pipeline.build().

    The actual implementation lives in stageflow.pipeline.dag
    but we use a protocol here to avoid circular imports.
    """

    stage_specs: list[UnifiedStageSpec]

    async def run(self, ctx: PipelineContext | StageContext) -> PipelineResults:
        ...


__all__ = [
    "Pipeline",
    "PipelineResults",
    "UnifiedStageSpec",
    "UnifiedStageGraph",
    "run_stage",
    "stage",
]
