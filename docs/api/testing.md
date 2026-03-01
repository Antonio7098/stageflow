# Testing API Reference

This page documents the APIs currently exported by `stageflow.testing`.

## Exports

```python
from stageflow.testing import (
    create_test_snapshot,
    create_test_stage_context,
    create_test_pipeline_context,
)

# Backward-compatible alias exported from root package:
from stageflow import create_test_context  # alias of create_test_stage_context
```

## create_test_snapshot

```python
create_test_snapshot(
    *,
    pipeline_run_id: UUID | None = None,
    request_id: UUID | None = None,
    session_id: UUID | None = None,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
    interaction_id: UUID | None = None,
    topology: str | None = "test",
    execution_mode: str | None = "test",
    input_text: str | None = None,
    messages: list[Message] | None = None,
    extensions: Any | None = None,
    **kwargs: Any,
) -> ContextSnapshot
```

## create_test_stage_context

```python
create_test_stage_context(
    *,
    snapshot: ContextSnapshot | None = None,
    inputs: StageInputs | None = None,
    prior_outputs: dict[str, StageOutput] | None = None,
    ports: CorePorts | LLMPorts | AudioPorts | None = None,
    stage_name: str = "test_stage",
    event_sink: Any | None = None,
    declared_deps: frozenset[str] | None = None,
    **snapshot_kwargs: Any,
) -> StageContext
```

## create_test_pipeline_context

```python
create_test_pipeline_context(
    *,
    pipeline_run_id: UUID | None = None,
    request_id: UUID | None = None,
    session_id: UUID | None = None,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
    interaction_id: UUID | None = None,
    topology: str | None = "test",
    execution_mode: str | None = "test",
    service: str = "test",
    data: dict[str, Any] | None = None,
    event_sink: Any | None = None,
    **kwargs: Any,
) -> PipelineContext
```

## Example

```python
from stageflow.testing import create_test_snapshot, create_test_stage_context
from stageflow import StageOutput

snapshot = create_test_snapshot(input_text="hello")
ctx = create_test_stage_context(
    snapshot=snapshot,
    prior_outputs={"input": StageOutput.ok(text="hello")},
)

assert ctx.inputs.get_from("input", "text") == "hello"
```

## Notes

- `MockStage`, `TestPipelineBuilder`, `TestFixtures`, `run_stage_test`, and `run_pipeline_test` are not part of `stageflow.testing` exports.
- Use your project test helpers (for example `tests/utils/`) for additional fixtures and mocks.
