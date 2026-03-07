# Wide Events API Reference

This page documents the current wide-event APIs from `stageflow.observability`.

## Exports

```python
from stageflow.observability import (
    WideEventEmitter,
    emit_stage_wide_event,
    emit_pipeline_wide_event,
)
```

## WideEventEmitter

```python
WideEventEmitter(
    stage_event_type: str = "stage.wide",
    pipeline_event_type: str = "pipeline.wide",
)
```

### Methods

```python
emit_stage_event(*, ctx: PipelineContext, result: StageResult, extra: Mapping[str, Any] | None = None) -> None
emit_pipeline_event(
    *,
    ctx: PipelineContext,
    stage_results: Mapping[str, StageResult],
    pipeline_name: str | None = None,
    status: str | None = None,
    duration_ms: int | None = None,
    started_at: datetime | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None
```

### Payload builders

```python
build_stage_payload(*, ctx, result, extra=None) -> dict[str, Any]
build_pipeline_payload(*, ctx, stage_results, pipeline_name=None, status=None, duration_ms=None, started_at=None, extra=None) -> dict[str, Any]
```

## Convenience functions

```python
emit_stage_wide_event(*, ctx, result, emitter=None, extra=None) -> None
emit_pipeline_wide_event(*, ctx, stage_results, emitter=None, pipeline_name=None, status=None, duration_ms=None, started_at=None, extra=None) -> None
```

## Stage event payload shape

```json
{
  "pipeline_run_id": "string|null",
  "request_id": "string|null",
  "session_id": "string|null",
  "user_id": "string|null",
  "org_id": "string|null",
  "topology": "string|null",
  "execution_mode": "string|null",
  "service": "string",
  "stage": "string",
  "status": "ok|skip|cancel|fail|retry|completed|failed",
  "started_at": "ISO datetime",
  "ended_at": "ISO datetime",
  "duration_ms": "number",
  "error": "string|null",
  "data_keys": ["string"]
}
```

## Pipeline event payload shape

```json
{
  "pipeline_run_id": "string|null",
  "request_id": "string|null",
  "session_id": "string|null",
  "user_id": "string|null",
  "org_id": "string|null",
  "topology": "string|null",
  "execution_mode": "string|null",
  "service": "string",
  "pipeline_name": "string",
  "status": "completed|failed|custom",
  "duration_ms": "number|null",
  "stage_counts": {"status": "count"},
  "stage_details": [
    {
      "stage": "string",
      "status": "string",
      "started_at": "ISO datetime",
      "ended_at": "ISO datetime",
      "duration_ms": "number",
      "error": "string|null",
      "data_keys": ["string"]
    }
  ]
}
```

## Pipeline integration

`Pipeline.run()` and `Pipeline.build()` both support wide-event emission directly.

```python
from stageflow.api import Pipeline, PipelineContext
from stageflow.observability import WideEventEmitter

pipeline = Pipeline(name="example").with_stage("llm", LLMStage)

await pipeline.run(
    PipelineContext(topology="example"),
    emit_stage_wide_events=True,
    emit_pipeline_wide_event=True,
    wide_event_emitter=WideEventEmitter(),
)
```
