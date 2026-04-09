# Pipeline API Reference

Stageflow provides one canonical graph executor and one deprecated compatibility executor:

- `UnifiedStageGraph` (recommended default)
- `StageGraph` (deprecated compatibility)

Use `UnifiedStageGraph` for all new pipelines. It executes stages with
`StageContext` + `StageInputs`, so stage code can safely use `ctx.inputs`.

## Pipeline (Unified graph)

```python
from stageflow.api import Pipeline, stage
```

```python
Pipeline(name: str = "pipeline", stages: dict[str, UnifiedStageSpec] = {})
```

### with_stage

```python
with_stage(
    name: str,
    runner: type[Stage] | Stage | Callable[[StageContext], Awaitable[StageOutput | dict[str, Any] | None]],
    kind: StageKind | str | None = None,
    dependencies: tuple[str, ...] | list[str] | None = None,
    *,
    after: str | Sequence[str] | None = None,
    conditional: bool = False,
    config: dict[str, Any] | None = None,
) -> Pipeline
```

If `kind` is omitted, Stageflow infers it from `runner.kind`.

`runner` may be:

- a stage class
- a stage instance
- a plain async callable accepting `StageContext`

Dependency syntax guidance:

- use `after=` for simple single-edge tutorial/script pipelines
- use `dependencies=` for multi-edge joins or when you want the full DAG edge list to stay explicit

### with_stages / from_stages / stage

```python
stage(name: str, runner: type[Stage] | Stage | Callable[[StageContext], Awaitable[StageOutput | dict[str, Any] | None]], kind: StageKind | str | None = None, *, after: str | Sequence[str] | None = None, ...) -> UnifiedStageSpec
with_stages(*specs: UnifiedStageSpec) -> Pipeline
from_stages(*specs: UnifiedStageSpec, name: str = "pipeline") -> Pipeline
```

These helpers give you a lower-ceremony, dependency-explicit way to define a
pipeline:

```python
pipeline = Pipeline.from_stages(
    stage("greet", GreetStage),
    stage("shout", ShoutStage, after="greet"),
)
```

### build

```python
build(
    *,
    interceptors: list[BaseInterceptor] | None = None,
    guard_retry_strategy: GuardRetryStrategy | None = None,
    emit_stage_wide_events: bool = False,
    emit_pipeline_wide_event: bool = False,
    wide_event_emitter: WideEventEmitter | None = None,
) -> UnifiedStageGraph
```

`Pipeline.build()` is the canonical builder entrypoint. It:

- validates empty pipelines, missing dependencies, and cycles before execution
- accepts custom interceptor stacks via `interceptors=[...]`
- can emit stage-wide and pipeline-wide observability events directly

```python
from stageflow.advanced import get_default_interceptors
from stageflow.observability import WideEventEmitter

graph = pipeline.build(
    interceptors=get_default_interceptors(include_auth=True),
    emit_stage_wide_events=True,
    emit_pipeline_wide_event=True,
    wide_event_emitter=WideEventEmitter(),
)
```

### run

```python
run(
    ctx: PipelineContext | StageContext | None = None,
    *,
    interceptors: list[BaseInterceptor] | None = None,
    guard_retry_strategy: GuardRetryStrategy | None = None,
    emit_stage_wide_events: bool = False,
    emit_pipeline_wide_event: bool = False,
    wide_event_emitter: WideEventEmitter | None = None,
    **context_kwargs: Any,
) -> PipelineResults
```

`Pipeline.run(...)` is the canonical entrypoint for application code.
It builds a `UnifiedStageGraph` and executes it for you.

```python
results = await pipeline.run(input_text="hello")
print(results.data("shout"))
```

`PipelineResults` also includes helpers such as:

- `results.output("stage")`
- `results.data("stage")`
- `results.require("stage")`
- `results.require_ok("stage")`
- `results.ok("stage")`

Use `build()` when you want to keep a reusable graph object or configure it once
and run it multiple times.

### invoke

```python
invoke(
    input_text_or_ctx: str | PipelineContext | StageContext | None = None,
    *,
    interceptors: list[BaseInterceptor] | None = None,
    guard_retry_strategy: GuardRetryStrategy | None = None,
    emit_stage_wide_events: bool = False,
    emit_pipeline_wide_event: bool = False,
    wide_event_emitter: WideEventEmitter | None = None,
    **context_kwargs: Any,
) -> PipelineResults
```

`Pipeline.invoke(...)` is a small alias for `run(...)` that accepts positional
input text. Prefer `run(...)` in docs and reusable application code; keep
`invoke(...)` for scripts or call sites where a positional input string reads
more naturally:

```python
results = await pipeline.invoke("hello")
```

### run_stage

```python
run_stage(
    name: str,
    runner: type[Stage] | Stage | Callable[[StageContext], Awaitable[StageOutput | dict[str, Any] | None]],
    kind: StageKind | str | None = None,
    **context_kwargs: Any,
) -> StageOutput
```

Use `run_stage(...)` for quick single-stage smoke tests or tiny scripts.

Callable example:

```python
async def echo(ctx: StageContext) -> StageOutput:
    return StageOutput.ok(data={"input": ctx.snapshot.input_text})

output = await run_stage("echo", echo, StageKind.TRANSFORM, input_text="hello")
```

### Additional helpers

```python
get_stage(name: str) -> UnifiedStageSpec | None
has_stage(name: str) -> bool
stage_names() -> list[str]
compose(other: Pipeline) -> Pipeline
```

`compose()` preserves identical stage definitions and raises `PipelineValidationError`
when same-named stages have conflicting specs.

## PipelineBuilder (Deprecated StageGraph compatibility)

```python
from stageflow.advanced import PipelineBuilder
```

`PipelineBuilder` is deprecated and returns the legacy `StageGraph` executor.
Use it only to keep older call sites working while you migrate them.
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

- Use `stageflow.api` when you want the smallest practical public surface.
- Use `Pipeline(...).run(...)` for the canonical new-code path.
- Use `Pipeline(...).invoke(...)` only as a convenience alias for small scripts.
- Use `Pipeline(...).build()` when you want an explicit reusable `UnifiedStageGraph`.
- Keep `PipelineBuilder(...).build()` (`StageGraph`) only for deprecated flows you
  have not migrated yet.

## Note on root imports

`PipelineBuilder` remains available from `stageflow.pipeline` for migration work,
but it is not the preferred entrypoint for new code.

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
- Currently targets the deprecated `PipelineBuilder` compatibility path.
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
