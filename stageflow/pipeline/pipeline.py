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
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from stageflow.core import Stage, StageKind


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


@dataclass
class Pipeline:
    """Builder for composing stages into a pipeline DAG.

    Provides a fluent API for adding stages, composing pipelines,
    and     building executable UnifiedStageGraph instances.

    Attributes:
        stages: Mapping of stage name -> UnifiedStageSpec
    """

    stages: dict[str, UnifiedStageSpec] = field(default_factory=dict)

    def with_stage(
        self,
        name: str,
        runner: type[Stage] | Stage,
        kind: StageKind,
        dependencies: tuple[str, ...] | None = None,
        conditional: bool = False,
    ) -> Pipeline:
        """Add a stage to this pipeline (fluent builder).

        Args:
            name: Unique stage name within the pipeline
            runner: Stage class or instance to execute
            kind: StageKind categorization
            dependencies: Names of stages that must complete first
            conditional: If True, stage may be skipped based on context

            Returns:
            Self for method chaining
        """
        spec = UnifiedStageSpec(
            name=name,
            runner=runner,
            kind=kind,
            dependencies=dependencies or (),
            conditional=conditional,
        )
        # Create new Pipeline instance to maintain immutability
        new_pipeline = Pipeline(stages=dict(self.stages))
        new_pipeline.stages[name] = spec
        return new_pipeline

    def compose(self, other: Pipeline) -> Pipeline:
        """Merge stages and dependencies from another pipeline.

        Stages from the other pipeline are added to this pipeline.
        If stage names conflict, the other pipeline's stage wins.

        Args:
            other: Another Pipeline instance to merge

            Returns:
            New Pipeline with merged stages
        """
        merged_stages = dict(self.stages)
        merged_stages.update(other.stages)
        return Pipeline(stages=merged_stages)

    def build(self) -> UnifiedStageGraph:
        """Generate executable DAG for the orchestrator.

        Creates a UnifiedStageGraph from the stage specifications.
        Validates that at least one stage exists and dependencies
        are resolvable.

        Returns:
            UnifiedStageGraph ready for orchestration

        Raises:
            ValueError: If pipeline is empty or dependencies are invalid
        """
        if not self.stages:
            raise ValueError("UnifiedStageGraph requires at least one UnifiedStageSpec")

        # Convert stage classes to callables for UnifiedStageGraph
        specs_for_graph = []
        for spec in self.stages.values():
            if isinstance(spec.runner, type):
                # It's a stage class, create a callable wrapper
                stage_class = spec.runner

                async def runner_wrapper(ctx, stage_cls=stage_class):
                    stage_instance = stage_cls()
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

        return UnifiedStageGraph(specs=specs_for_graph)  # type: ignore


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
