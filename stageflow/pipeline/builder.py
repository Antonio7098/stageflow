"""Pipeline builder for code-defined DAG composition with validation.

This module provides an enhanced Pipeline class with DAG validation,
cycle detection, and composition capabilities.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stageflow.observability.wide_events import WideEventEmitter
    from stageflow.pipeline.dag import StageGraph

from stageflow.pipeline.spec import (
    CycleDetectedError,
    PipelineSpec,
    PipelineValidationError,
    StageRunner,
)


@dataclass
class PipelineBuilder:
    """Code-defined pipeline with typed composition and validation.

    Provides a fluent API for adding stages, composing pipelines,
    and building executable StageGraph instances with full DAG validation.

    Attributes:
        name: Pipeline name for identification
        stages: Mapping of stage name -> PipelineSpec
    """

    name: str = "pipeline"
    stages: dict[str, PipelineSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate pipeline after initialization."""
        if self.stages:
            self._validate()

    def _validate(self) -> None:
        """Ensure DAG validity: all dependencies exist, no cycles.

        Raises:
            PipelineValidationError: If validation fails
        """
        # Check all dependencies reference existing stages
        for stage_name, spec in self.stages.items():
            for dep in spec.dependencies:
                if dep not in self.stages:
                    raise PipelineValidationError(
                        f"Stage '{stage_name}' depends on '{dep}' which does not exist",
                        stages=[stage_name, dep],
                    )

        # Check for cycles using Kahn's algorithm (topological sort)
        self._detect_cycles()

    def _detect_cycles(self) -> None:
        """Detect cycles in the pipeline DAG using DFS with cycle path extraction.

        Raises:
            CycleDetectedError: If a cycle is detected, with the cycle path
        """
        if not self.stages:
            return

        # Use DFS to detect cycles and extract the cycle path
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = dict.fromkeys(self.stages, WHITE)
        parent: dict[str, str | None] = dict.fromkeys(self.stages)

        def dfs(node: str, path: list[str]) -> list[str] | None:
            """DFS that returns cycle path if found, None otherwise."""
            color[node] = GRAY
            path.append(node)

            # Visit all nodes that depend on this node (reverse edges for cycle detection)
            for name, spec in self.stages.items():
                if node in spec.dependencies:  # name depends on node
                    if color[name] == GRAY:
                        # Found cycle - extract path from name back to name
                        cycle_start = path.index(name) if name in path else 0
                        cycle_path = path[cycle_start:] + [name]
                        return cycle_path
                    elif color[name] == WHITE:
                        parent[name] = node
                        result = dfs(name, path)
                        if result:
                            return result

            path.pop()
            color[node] = BLACK
            return None

        # Also check forward direction: for each stage, check its dependencies
        def dfs_forward(node: str, path: list[str]) -> list[str] | None:
            """DFS following dependency edges."""
            color[node] = GRAY
            path.append(node)

            spec = self.stages[node]
            for dep in spec.dependencies:
                if dep not in self.stages:
                    continue  # Skip missing deps, handled elsewhere
                if color[dep] == GRAY:
                    # Found cycle
                    cycle_start = path.index(dep)
                    cycle_path = path[cycle_start:] + [dep]
                    return cycle_path
                elif color[dep] == WHITE:
                    result = dfs_forward(dep, path)
                    if result:
                        return result

            path.pop()
            color[node] = BLACK
            return None

        # Reset and run forward DFS
        color = dict.fromkeys(self.stages, WHITE)
        for name in self.stages:
            if color[name] == WHITE:
                cycle_path = dfs_forward(name, [])
                if cycle_path:
                    raise CycleDetectedError(
                        cycle_path=cycle_path,
                        stages=list(set(cycle_path)),
                    )

    def with_stage(
        self,
        name: str,
        runner: type[StageRunner] | StageRunner,
        dependencies: tuple[str, ...] | list[str] | None = None,
        inputs: tuple[str, ...] | list[str] | None = None,
        outputs: tuple[str, ...] | list[str] | None = None,
        conditional: bool = False,
        args: dict[str, Any] | None = None,
    ) -> PipelineBuilder:
        """Add a stage to this pipeline (fluent builder).

        Args:
            name: Unique stage name within the pipeline
            runner: Stage class or instance implementing StageRunner
            dependencies: Names of stages that must complete first
            inputs: Keys this stage reads from context
            outputs: Keys this stage writes to context
            conditional: If True, stage may be skipped based on context
            args: Additional arguments for the stage

        Returns:
            New PipelineBuilder with the added stage (immutable pattern)
        """
        deps = tuple(dependencies) if dependencies else ()
        ins = tuple(inputs) if inputs else ()
        outs = tuple(outputs) if outputs else ()

        spec = PipelineSpec(
            name=name,
            runner=runner,
            dependencies=deps,
            inputs=ins,
            outputs=outs,
            conditional=conditional,
            args=args or {},
        )

        # Create new dict with existing stages plus new one
        new_stages = dict(self.stages)
        new_stages[name] = spec

        return PipelineBuilder(name=self.name, stages=new_stages)

    def compose(self, other: PipelineBuilder) -> PipelineBuilder:
        """Merge stages from another pipeline, resolving dependencies.

        Args:
            other: Another PipelineBuilder to merge

        Returns:
            New PipelineBuilder with merged stages

        Raises:
            PipelineValidationError: If stage names conflict with different specs
        """
        merged_stages = dict(self.stages)

        for name, spec in other.stages.items():
            if name in merged_stages:
                existing = merged_stages[name]
                # Check if specs are equivalent (same runner, dependencies, etc.)
                if (
                    existing.runner != spec.runner
                    or existing.dependencies != spec.dependencies
                    or existing.conditional != spec.conditional
                ):
                    raise PipelineValidationError(
                        f"Stage '{name}' exists in both pipelines with different specs",
                        stages=[name],
                    )
            else:
                merged_stages[name] = spec

        composed = PipelineBuilder(
            name=f"{self.name}+{other.name}",
            stages=merged_stages,
        )
        # Validation happens in __post_init__
        return composed

    def build(
        self,
        *,
        emit_stage_wide_events: bool = False,
        emit_pipeline_wide_event: bool = False,
        wide_event_emitter: WideEventEmitter | None = None,
    ) -> StageGraph:
        """Generate executable DAG for the orchestrator.

        Creates a StageGraph from the pipeline specifications.
        Validates that at least one stage exists.

        Returns:
            StageGraph ready for orchestration

        Raises:
            ValueError: If pipeline is empty
        """
        if not self.stages:
            raise ValueError("Cannot build empty pipeline")

        from stageflow.pipeline.dag import StageGraph, StageSpec

        # Convert PipelineSpec to StageSpec for StageGraph
        graph_specs: list[StageSpec] = []

        for spec in self.stages.values():
            # Create a runner callable that instantiates and executes the stage
            runner = spec.runner
            if isinstance(runner, type):
                # It's a class, create wrapper that instantiates it
                stage_class = runner

                async def create_runner(ctx, cls=stage_class, stage_args=spec.args):
                    instance = cls(**stage_args) if stage_args else cls()
                    return await instance.execute(ctx)

                callable_runner = create_runner
            else:
                # It's already an instance
                stage_instance = runner

                async def create_runner(ctx, stage=stage_instance):
                    return await stage.execute(ctx)

                callable_runner = create_runner

            graph_spec = StageSpec(
                name=spec.name,
                runner=callable_runner,
                dependencies=spec.dependencies,
                conditional=spec.conditional,
            )
            graph_specs.append(graph_spec)

        return StageGraph(
            specs=graph_specs,
            wide_event_emitter=wide_event_emitter,
            emit_stage_wide_events=emit_stage_wide_events,
            emit_pipeline_wide_event=emit_pipeline_wide_event,
        )

    def get_stage(self, name: str) -> PipelineSpec | None:
        """Get a stage specification by name.

        Args:
            name: Stage name to look up

        Returns:
            PipelineSpec if found, None otherwise
        """
        return self.stages.get(name)

    def has_stage(self, name: str) -> bool:
        """Check if a stage exists in the pipeline.

        Args:
            name: Stage name to check

        Returns:
            True if stage exists
        """
        return name in self.stages

    def stage_names(self) -> list[str]:
        """Get stage names in topological order.

        Returns:
            List of stage names sorted topologically
        """
        if not self.stages:
            return []

        # Topological sort using Kahn's algorithm
        in_degree = {name: len(set(spec.dependencies)) for name, spec in self.stages.items()}
        queue: deque[str] = deque()
        result: list[str] = []

        for name, count in in_degree.items():
            if count == 0:
                queue.append(name)

        while queue:
            node = queue.popleft()
            result.append(node)

            for name, spec in self.stages.items():
                if node in spec.dependencies:
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        queue.append(name)

        return result

    def __repr__(self) -> str:
        return f"PipelineBuilder(name={self.name!r}, stages={list(self.stages.keys())})"


__all__ = [
    "PipelineBuilder",
]
