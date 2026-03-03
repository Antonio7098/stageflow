# Pipeline API Reference

Stageflow provides two graph executors:

- `UnifiedStageGraph` (recommended default)
- `StageGraph` (legacy compatibility)

Use `UnifiedStageGraph` for all new pipelines. It executes stages with
`StageContext` + `StageInputs`, so stage code can safely use `ctx.inputs`.

## Pipeline (Unified graph)

```python
from stageflow import Pipeline, StageKind
```

```python
Pipeline(name: str = "pipeline", stages: dict[str, UnifiedStageSpec] = {})
```

### with_stage

```python
with_stage(
    name: str,
    runner: type[Stage] | Stage,
    kind: StageKind,
    dependencies: tuple[str, ...] | None = None,
    conditional: bool = False,
    config: dict[str, Any] | None = None,
) -> Pipeline
```

### build

```python
build(
    *,
    interceptors: list[BaseInterceptor] | None = None,
    guard_retry_strategy: GuardRetryStrategy | None = None,
) -> UnifiedStageGraph
```

`Pipeline.build()` does not accept wide-event flags.
It accepts custom interceptor stacks via `interceptors=[...]`.

```python
from stageflow import get_default_interceptors

graph = pipeline.build(
    interceptors=get_default_interceptors(include_auth=True),
)
```

## PipelineBuilder (StageGraph)

```python
from stageflow.pipeline import PipelineBuilder
```

`PipelineBuilder` returns the legacy `StageGraph` executor.
Use it only when you need legacy-only options (for example wide-event emission).
In `StageGraph`, stages receive `PipelineContext`, not `StageContext`.

```python
builder = PipelineBuilder(name="example")
# ... with_stage(...)

graph = builder.build(
    emit_stage_wide_events=True,
    emit_pipeline_wide_event=True,
    wide_event_emitter=WideEventEmitter(),
)
```

## Which One Should I Use?

- Use `Pipeline(...).build()` (`UnifiedStageGraph`) for new code.
- Keep `PipelineBuilder(...).build()` (`StageGraph`) only for legacy flows you have
  not migrated yet.

## Note on root imports

`PipelineBuilder` is available from `stageflow.pipeline`. Prefer that import path for clarity.

## Duplex Topology Helpers

```python
from stageflow.pipeline import (
    DuplexLaneSpec,
    DuplexSystemSpec,
    FluentPipelineBuilder,
    with_duplex_system,
)
```

### DuplexLaneSpec

```python
DuplexLaneSpec(
    stages: tuple[tuple[str, StageRunner], ...],
    depends_on: tuple[str, ...] = (),
)
```

- Defines one directional lane.
- `stages` must contain at least one stage.
- The first stage in the lane depends on `depends_on`; each next stage depends on the previous stage.

### DuplexSystemSpec

```python
DuplexSystemSpec(
    forward: DuplexLaneSpec,
    reverse: DuplexLaneSpec,
    join_stage: tuple[str, StageRunner] | None = None,
    join_depends_on: tuple[str, ...] = (),
)
```

- Defines a bidirectional topology.
- `join_stage` (optional) converges both lane tails.
- `join_depends_on` appends extra dependencies to the join stage.

### with_duplex_system

```python
with_duplex_system(builder: PipelineBuilder, system: DuplexSystemSpec) -> PipelineBuilder
```

- Adds both lanes and optional join stage.
- Validates duplicate stage names and collisions with existing builder stage names.

### FluentPipelineBuilder.duplex

```python
duplex(
    *,
    forward: tuple[tuple[str, StageRunner], ...] | list[tuple[str, StageRunner]],
    reverse: tuple[tuple[str, StageRunner], ...] | list[tuple[str, StageRunner]],
    forward_depends_on: tuple[str, ...] | None = None,
    reverse_depends_on: tuple[str, ...] | None = None,
    join_stage: tuple[str, StageRunner] | None = None,
    join_depends_on: tuple[str, ...] | None = None,
) -> FluentPipelineBuilder
```

- Convenience wrapper over `with_duplex_system`.
- If dependency args are omitted and the fluent builder already has a tail stage, both lanes auto-depend on that tail.
