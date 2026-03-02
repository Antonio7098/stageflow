# Pipeline API Reference

Stageflow provides two builders with different output graphs.

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
build(*, guard_retry_strategy: GuardRetryStrategy | None = None) -> UnifiedStageGraph
```

`Pipeline.build()` does not accept wide-event flags.

## PipelineBuilder (StageGraph)

```python
from stageflow.pipeline import PipelineBuilder
```

Use `PipelineBuilder` when you need StageGraph options like wide-event emission.

```python
builder = PipelineBuilder(name="example")
# ... with_stage(...)

graph = builder.build(
    emit_stage_wide_events=True,
    emit_pipeline_wide_event=True,
    wide_event_emitter=WideEventEmitter(),
)
```

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
