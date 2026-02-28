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
