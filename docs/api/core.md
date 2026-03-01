# Core Types API Reference

## Stage

```python
from stageflow import Stage
```

A stage implements:

- `name: str`
- `kind: StageKind`
- `async execute(ctx: StageContext) -> StageOutput`

## StageKind

```python
from stageflow import StageKind
```

Values: `TRANSFORM`, `ENRICH`, `ROUTE`, `GUARD`, `WORK`, `AGENT`.

## StageStatus

```python
from stageflow import StageStatus
```

Values: `OK`, `SKIP`, `CANCEL`, `FAIL`, `RETRY`.

## StageOutput

```python
from stageflow import StageOutput, StageArtifact, StageEvent
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
from stageflow import StageContext
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
- `as_pipeline_context(...) -> PipelineContext`
- `now() -> datetime` (classmethod)

Artifacts are returned via `StageOutput.artifacts`; they are not accumulated through context mutators.
