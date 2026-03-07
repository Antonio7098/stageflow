# Core Types API Reference

## Stage

```python
from stageflow.api import Stage, stage_metadata
```

A stage implements:

- `name: str`
- `kind: StageKind`
- `async execute(ctx: StageContext) -> StageReturn`

You can attach `name` and `kind` either as class attributes or with the
`@stage_metadata(...)` decorator.

## StageReturn

```python
from stageflow.api import StageReturn
```

`StageReturn = StageOutput | dict[str, Any] | None`

- return a plain `dict` for the common happy path
- return `StageOutput` when you need explicit status, error, artifact, or event semantics
- return `None` when an empty successful payload is enough

## StageKind

```python
from stageflow.api import StageKind
```

Values: `TRANSFORM`, `ENRICH`, `ROUTE`, `GUARD`, `WORK`, `AGENT`.

## StageStatus

```python
from stageflow.api import StageStatus
```

Values: `OK`, `SKIP`, `CANCEL`, `FAIL`, `RETRY`.

## StageOutput

```python
from stageflow.api import StageOutput, StageArtifact, StageEvent
```

### Attributes

- `status: StageStatus`
- `data: dict[str, Any]`
- `artifacts: list[StageArtifact]`
- `events: list[StageEvent]`
- `error: str | None`
- `duration_ms: int | None`
- `version: str | None`

### Constructors

```python
StageOutput.ok(data: dict[str, Any] | None = None, *, version: str | None = None, **kwargs)
StageOutput.skip(reason: str = "", data: dict[str, Any] | None = None, *, version: str | None = None)
StageOutput.cancel(reason: str = "", data: dict[str, Any] | None = None, *, version: str | None = None)
StageOutput.fail(error: str | None = None, data: dict[str, Any] | None = None, *, response: str | None = None, version: str | None = None)
StageOutput.retry(error: str, data: dict[str, Any] | None = None, *, version: str | None = None)
```

## StageContext

```python
from stageflow.api import StageContext
```

### Constructor

```python
StageContext(
    snapshot: ContextSnapshot,
    inputs: StageInputs,
    stage_name: str,
    timer: PipelineTimer,
    event_sink: EventSink | None = None,
)
```

### Properties

- `snapshot`
- `inputs`
- `stage_name`
- `timer`
- `event_sink`
- `started_at`
- `pipeline_run_id`
- `request_id`
- `execution_mode`

### Methods

- `to_dict() -> dict[str, Any]`
- `try_emit_event(type: str, data: dict[str, Any]) -> None`
- `emit_event(type: str, data: dict[str, Any]) -> None` (alias)
- `record_stage_event(stage: str, status: str, **kwargs) -> None`
- `as_pipeline_context(...) -> PipelineContext` (deprecated; prefer `PipelineContext.from_snapshot(...)` when bridging back to orchestration code)
- `now() -> datetime` (classmethod)

`StageContext` is a runtime wrapper, not the recommended pipeline entrypoint.
Artifacts are returned via `StageOutput.artifacts`; they are not accumulated through context mutators.
