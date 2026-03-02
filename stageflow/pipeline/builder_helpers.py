"""Pipeline builder helpers for ergonomic DAG construction.

Provides utilities for building deep/wide DAGs with minimal boilerplate,
including duplex systems, linear chain generation, and parallel stage factories.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from stageflow.pipeline.builder import PipelineBuilder
from stageflow.pipeline.spec import StageRunner

T = TypeVar("T")
DuplexStage = tuple[str, StageRunner]


@dataclass(frozen=True, slots=True)
class DuplexLaneSpec:
    """Directional lane specification for a duplex system."""

    stages: tuple[DuplexStage, ...]
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.stages:
            raise ValueError("DuplexLaneSpec requires at least one stage")


@dataclass(frozen=True, slots=True)
class DuplexSystemSpec:
    """Bidirectional topology specification with optional convergence stage."""

    forward: DuplexLaneSpec
    reverse: DuplexLaneSpec
    join_stage: DuplexStage | None = None
    join_depends_on: tuple[str, ...] = ()


def _dedupe_names(names: tuple[str, ...]) -> tuple[str, ...]:
    """Preserve ordering while removing duplicate names."""
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return tuple(ordered)


def _append_lane(
    builder: PipelineBuilder,
    lane: DuplexLaneSpec,
) -> tuple[PipelineBuilder, str]:
    """Append a directional lane and return updated builder + lane tail stage."""
    result = builder
    previous_name: str | None = None

    for index, (stage_name, stage_runner) in enumerate(lane.stages):
        dependencies = lane.depends_on if index == 0 else (previous_name,) if previous_name else ()
        result = result.with_stage(
            name=stage_name,
            runner=stage_runner,
            dependencies=dependencies,
        )
        previous_name = stage_name

    if previous_name is None:
        raise ValueError("Duplex lane must contain at least one stage")

    return result, previous_name


def with_duplex_system(
    builder: PipelineBuilder,
    system: DuplexSystemSpec,
) -> PipelineBuilder:
    """Add a duplex (bidirectional) topology to a pipeline.

    A duplex system has two independent directional lanes:
    - `forward`: linear chain from source A to destination B
    - `reverse`: linear chain from source B back to source A

    Optionally, a `join_stage` can converge both lane tails.

    Example:
        ```python
        system = DuplexSystemSpec(
            forward=DuplexLaneSpec(
                stages=(
                    ("uplink_decode", DecodeStage()),
                    ("uplink_transform", TransformStage()),
                ),
                depends_on=("ingress_a",),
            ),
            reverse=DuplexLaneSpec(
                stages=(
                    ("downlink_decode", DecodeStage()),
                    ("downlink_transform", TransformStage()),
                ),
                depends_on=("ingress_b",),
            ),
            join_stage=("sync", SyncStage()),
        )
        pipeline = with_duplex_system(PipelineBuilder("duplex"), system)
        ```
    """
    all_stage_names = [
        stage_name
        for lane in (system.forward, system.reverse)
        for stage_name, _ in lane.stages
    ]
    if system.join_stage:
        all_stage_names.append(system.join_stage[0])

    introduced_names = set(all_stage_names)
    seen_names: set[str] = set()
    duplicates: set[str] = set()
    for stage_name in all_stage_names:
        if stage_name in seen_names:
            duplicates.add(stage_name)
        else:
            seen_names.add(stage_name)
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise ValueError(f"Duplex system contains duplicate stage names: {duplicate_list}")

    collisions = introduced_names.intersection(builder.stages)
    if collisions:
        collision_list = ", ".join(sorted(collisions))
        raise ValueError(f"Duplex system stage names already exist in builder: {collision_list}")

    result, forward_tail = _append_lane(builder, system.forward)
    result, reverse_tail = _append_lane(result, system.reverse)

    if system.join_stage:
        join_name, join_runner = system.join_stage
        join_dependencies = _dedupe_names((forward_tail, reverse_tail, *system.join_depends_on))
        result = result.with_stage(
            name=join_name,
            runner=join_runner,
            dependencies=join_dependencies,
        )

    return result


def with_linear_chain(
    builder: PipelineBuilder,
    count: int,
    stage_factory: Callable[[int], tuple[str, StageRunner]],
    *,
    first_depends_on: tuple[str, ...] | None = None,
) -> PipelineBuilder:
    """Add a linear chain of stages to a pipeline.

    Creates `count` stages where each depends on the previous one,
    forming a sequential chain.

    Args:
        builder: Pipeline builder to add stages to
        count: Number of stages in the chain
        stage_factory: Function(index) -> (name, runner) for each stage
        first_depends_on: Dependencies for the first stage in the chain

    Returns:
        New PipelineBuilder with the chain added

    Example:
        ```python
        def make_transform(i: int) -> tuple[str, StageRunner]:
            return f"transform_{i}", TransformStage(config={"index": i})

        pipeline = (
            PipelineBuilder("chain_example")
            .with_stage("input", InputStage())
        )
        pipeline = with_linear_chain(
            pipeline,
            count=5,
            stage_factory=make_transform,
            first_depends_on=("input",),
        )
        ```
    """
    if count <= 0:
        return builder

    result = builder
    prev_name: str | None = None

    for i in range(count):
        name, runner = stage_factory(i)

        # Determine dependencies
        deps = first_depends_on or () if i == 0 else (prev_name,) if prev_name else ()

        result = result.with_stage(
            name=name,
            runner=runner,
            dependencies=deps,
        )
        prev_name = name

    return result


def with_parallel_stages(
    builder: PipelineBuilder,
    count: int,
    stage_factory: Callable[[int], tuple[str, StageRunner]],
    *,
    depends_on: tuple[str, ...] | None = None,
    _prefix: str = "parallel",
) -> PipelineBuilder:
    """Add parallel stages to a pipeline.

    Creates `count` stages that all depend on the same upstream stages,
    enabling parallel execution.

    Args:
        builder: Pipeline builder to add stages to
        count: Number of parallel stages
        stage_factory: Function(index) -> (name, runner) for each stage
        depends_on: Common dependencies for all parallel stages
        prefix: Prefix for stage names if factory doesn't provide names

    Returns:
        New PipelineBuilder with parallel stages added

    Example:
        ```python
        def make_processor(i: int) -> tuple[str, StageRunner]:
            return f"processor_{i}", ProcessorStage(shard=i)

        pipeline = with_parallel_stages(
            builder,
            count=4,
            stage_factory=make_processor,
            depends_on=("splitter",),
        )
        ```
    """
    if count <= 0:
        return builder

    result = builder
    deps = depends_on or ()

    for i in range(count):
        name, runner = stage_factory(i)
        result = result.with_stage(
            name=name,
            runner=runner,
            dependencies=deps,
        )

    return result


def with_fan_out_fan_in(
    builder: PipelineBuilder,
    fan_out_stage: tuple[str, StageRunner],
    parallel_count: int,
    parallel_factory: Callable[[int], tuple[str, StageRunner]],
    fan_in_stage: tuple[str, StageRunner],
    *,
    fan_out_depends_on: tuple[str, ...] | None = None,
) -> PipelineBuilder:
    """Add a fan-out/fan-in pattern to a pipeline.

    Creates a single fan-out stage, multiple parallel stages, and
    a fan-in stage that depends on all parallel stages.

    Args:
        builder: Pipeline builder to add stages to
        fan_out_stage: (name, runner) for the fan-out stage
        parallel_count: Number of parallel stages
        parallel_factory: Function(index) -> (name, runner) for parallel stages
        fan_in_stage: (name, runner) for the fan-in stage
        fan_out_depends_on: Dependencies for the fan-out stage

    Returns:
        New PipelineBuilder with fan-out/fan-in pattern

    Example:
        ```python
        pipeline = with_fan_out_fan_in(
            builder,
            fan_out_stage=("splitter", SplitterStage()),
            parallel_count=4,
            parallel_factory=lambda i: (f"worker_{i}", WorkerStage(i)),
            fan_in_stage=("merger", MergerStage()),
            fan_out_depends_on=("input",),
        )
        ```
    """
    # Add fan-out stage
    fan_out_name, fan_out_runner = fan_out_stage
    result = builder.with_stage(
        name=fan_out_name,
        runner=fan_out_runner,
        dependencies=fan_out_depends_on or (),
    )

    # Add parallel stages
    parallel_names = []
    for i in range(parallel_count):
        name, runner = parallel_factory(i)
        parallel_names.append(name)
        result = result.with_stage(
            name=name,
            runner=runner,
            dependencies=(fan_out_name,),
        )

    # Add fan-in stage
    fan_in_name, fan_in_runner = fan_in_stage
    result = result.with_stage(
        name=fan_in_name,
        runner=fan_in_runner,
        dependencies=tuple(parallel_names),
    )

    return result


def with_conditional_branch(
    builder: PipelineBuilder,
    router_stage: tuple[str, StageRunner],
    branches: dict[str, tuple[str, StageRunner]],
    merge_stage: tuple[str, StageRunner] | None = None,
    *,
    router_depends_on: tuple[str, ...] | None = None,
) -> PipelineBuilder:
    """Add conditional branching to a pipeline.

    Creates a router stage and multiple conditional branches that
    execute based on router output.

    Args:
        builder: Pipeline builder to add stages to
        router_stage: (name, runner) for the routing stage
        branches: Dict of branch_name -> (stage_name, runner)
        merge_stage: Optional (name, runner) for merging branch outputs
        router_depends_on: Dependencies for the router stage

    Returns:
        New PipelineBuilder with conditional branching

    Example:
        ```python
        pipeline = with_conditional_branch(
            builder,
            router_stage=("classifier", ClassifierStage()),
            branches={
                "high_priority": ("urgent_handler", UrgentHandler()),
                "normal": ("normal_handler", NormalHandler()),
                "low_priority": ("batch_handler", BatchHandler()),
            },
            merge_stage=("response_builder", ResponseBuilder()),
            router_depends_on=("input",),
        )
        ```
    """
    # Add router stage
    router_name, router_runner = router_stage
    result = builder.with_stage(
        name=router_name,
        runner=router_runner,
        dependencies=router_depends_on or (),
    )

    # Add branch stages (conditional)
    branch_names = []
    for _branch_key, (stage_name, stage_runner) in branches.items():
        branch_names.append(stage_name)
        result = result.with_stage(
            name=stage_name,
            runner=stage_runner,
            dependencies=(router_name,),
            conditional=True,
        )

    # Add merge stage if provided
    if merge_stage:
        merge_name, merge_runner = merge_stage
        result = result.with_stage(
            name=merge_name,
            runner=merge_runner,
            dependencies=tuple(branch_names),
        )

    return result


class FluentPipelineBuilder:
    """Fluent wrapper for PipelineBuilder with helper methods.

    Provides a more ergonomic API for building complex pipelines.

    Example:
        ```python
        pipeline = (
            FluentPipelineBuilder("my_pipeline")
            .stage("input", InputStage())
            .linear_chain(5, lambda i: (f"transform_{i}", TransformStage(i)))
            .parallel(4, lambda i: (f"worker_{i}", WorkerStage(i)), depends_on=("transform_4",))
            .stage("output", OutputStage(), depends_on=("worker_0", "worker_1", "worker_2", "worker_3"))
            .build()
        )
        ```
    """

    def __init__(self, name: str) -> None:
        self._builder = PipelineBuilder(name=name)
        self._last_stage: str | None = None

    def stage(
        self,
        name: str,
        runner: StageRunner,
        *,
        depends_on: tuple[str, ...] | list[str] | None = None,
        conditional: bool = False,
    ) -> FluentPipelineBuilder:
        """Add a single stage."""
        self._builder = self._builder.with_stage(
            name=name,
            runner=runner,
            dependencies=tuple(depends_on) if depends_on else (),
            conditional=conditional,
        )
        self._last_stage = name
        return self

    def linear_chain(
        self,
        count: int,
        factory: Callable[[int], tuple[str, StageRunner]],
        *,
        first_depends_on: tuple[str, ...] | None = None,
    ) -> FluentPipelineBuilder:
        """Add a linear chain of stages."""
        # Use last stage as dependency if not specified
        deps = first_depends_on
        if deps is None and self._last_stage:
            deps = (self._last_stage,)

        self._builder = with_linear_chain(
            self._builder,
            count=count,
            stage_factory=factory,
            first_depends_on=deps,
        )

        # Update last stage to end of chain
        if count > 0:
            name, _ = factory(count - 1)
            self._last_stage = name

        return self

    def parallel(
        self,
        count: int,
        factory: Callable[[int], tuple[str, StageRunner]],
        *,
        depends_on: tuple[str, ...] | None = None,
    ) -> FluentPipelineBuilder:
        """Add parallel stages."""
        deps = depends_on
        if deps is None and self._last_stage:
            deps = (self._last_stage,)

        self._builder = with_parallel_stages(
            self._builder,
            count=count,
            stage_factory=factory,
            depends_on=deps,
        )

        # Last stage is ambiguous after parallel, clear it
        self._last_stage = None

        return self

    def fan_out_fan_in(
        self,
        fan_out: tuple[str, StageRunner],
        parallel_count: int,
        parallel_factory: Callable[[int], tuple[str, StageRunner]],
        fan_in: tuple[str, StageRunner],
    ) -> FluentPipelineBuilder:
        """Add fan-out/fan-in pattern."""
        deps = (self._last_stage,) if self._last_stage else None

        self._builder = with_fan_out_fan_in(
            self._builder,
            fan_out_stage=fan_out,
            parallel_count=parallel_count,
            parallel_factory=parallel_factory,
            fan_in_stage=fan_in,
            fan_out_depends_on=deps,
        )

        fan_in_name, _ = fan_in
        self._last_stage = fan_in_name

        return self

    def duplex(
        self,
        *,
        forward: tuple[DuplexStage, ...] | list[DuplexStage],
        reverse: tuple[DuplexStage, ...] | list[DuplexStage],
        forward_depends_on: tuple[str, ...] | None = None,
        reverse_depends_on: tuple[str, ...] | None = None,
        join_stage: DuplexStage | None = None,
        join_depends_on: tuple[str, ...] | None = None,
    ) -> FluentPipelineBuilder:
        """Add a duplex (bidirectional) system.

        If `forward_depends_on`/`reverse_depends_on` are omitted, both lanes
        depend on the current fluent tail stage when available.
        """
        auto_dep = (self._last_stage,) if self._last_stage else ()
        forward_deps = forward_depends_on if forward_depends_on is not None else auto_dep
        reverse_deps = reverse_depends_on if reverse_depends_on is not None else auto_dep

        system = DuplexSystemSpec(
            forward=DuplexLaneSpec(
                stages=tuple(forward),
                depends_on=forward_deps,
            ),
            reverse=DuplexLaneSpec(
                stages=tuple(reverse),
                depends_on=reverse_deps,
            ),
            join_stage=join_stage,
            join_depends_on=tuple(join_depends_on or ()),
        )
        self._builder = with_duplex_system(self._builder, system)
        self._last_stage = join_stage[0] if join_stage else None
        return self

    def build(self, **kwargs: Any) -> Any:
        """Build the pipeline graph."""
        return self._builder.build(**kwargs)

    @property
    def builder(self) -> PipelineBuilder:
        """Get the underlying PipelineBuilder."""
        return self._builder


__all__ = [
    "DuplexLaneSpec",
    "DuplexSystemSpec",
    "FluentPipelineBuilder",
    "with_conditional_branch",
    "with_duplex_system",
    "with_fan_out_fan_in",
    "with_linear_chain",
    "with_parallel_stages",
]
