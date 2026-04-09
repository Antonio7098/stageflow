# Context API Reference

## PipelineContext (Canonical User Context)

```python
from stageflow.api import PipelineContext
```

```python
PipelineContext(
    pipeline_run_id: UUID | None = None,
    request_id: UUID | None = None,
    session_id: UUID | None = None,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
    interaction_id: UUID | None = None,
    topology: str | None = None,
    execution_mode: str | None = None,
    input_text: str | None = None,
    input_audio_duration_ms: int | None = None,
    conversation: Conversation | None = None,
    enrichments: Enrichments | None = None,
    extensions: ExtensionBundle | dict[str, Any] | None = None,
    metadata: dict[str, Any] = {},
    configuration: dict[str, Any] = {},
    service: str = "pipeline",
    data: dict[str, Any] = {},
    ports: CorePorts | LLMPorts | AudioPorts | None = None,
    ...
)
```

Important APIs:
- `to_snapshot() -> ContextSnapshot`
- `create(...) -> PipelineContext`
- `from_snapshot(snapshot, ...) -> PipelineContext`
- `derive_root_stage_context(stage_name="__pipeline_root__") -> StageContext` (advanced/internal)
- `fork(..., inherit_data=False, data_overrides=None) -> PipelineContext`
- `mark_canceled(reason="Cancellation requested") -> None`
- `raise_if_cancelled() -> None`
- `cancellation_checkpoint() -> Awaitable[None]`
- `add_before_stage_start_hook(hook) -> None`

`PipelineContext` is the context users should create and pass into pipeline entrypoints.
For normal application code, `await pipeline.run(input_text=..., topology=...)`
is often enough; create `PipelineContext(...)` when you want explicit control
over metadata, ports, or correlation IDs.
`ContextSnapshot` and `StageContext` are derived execution views used by the runtime.
In the recommended `UnifiedStageGraph` path, stage `execute()` methods receive
`StageContext` (with `ctx.inputs`), not `PipelineContext`.

Use `ports=` on `PipelineContext` when you want the root graph entrypoint to pass
shared runtime capabilities into derived `StageContext.inputs.ports` values.

### Subpipeline Forking

`PipelineContext.fork(...)` now supports explicit child `data` propagation:

```python
child = parent_ctx.fork(
    child_run_id=uuid4(),
    parent_stage_id="fanout_worker",
    correlation_id=uuid4(),
    inherit_data=("timeout_ms", "idempotency_key"),
    data_overrides={"worker_id": "a"},
)
```

Rules:

- `inherit_data=False` keeps the child `data` dict empty.
- `inherit_data=True` copies the full parent `data` dict.
- `inherit_data=("key_a", "key_b")` copies only selected keys.
- `data_overrides=` is applied after inheritance.

Parent data is still available read-only through `get_parent_data(...)`.

## RunIdentity (Advanced)

```python
from stageflow.context import RunIdentity
```

```python
RunIdentity(
    pipeline_run_id: UUID | None = None,
    request_id: UUID | None = None,
    session_id: UUID | None = None,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
    interaction_id: UUID | None = None,
    created_at: datetime = auto,
)
```

## ContextSnapshot (Advanced)

```python
from stageflow.context import ContextSnapshot
```

```python
ContextSnapshot(
    run_id: RunIdentity = RunIdentity(),
    enrichments: Enrichments | None = None,
    conversation: Conversation | None = None,
    extensions: ExtensionBundle | None = None,
    input_text: str | None = None,
    input_audio_duration_ms: int | None = None,
    topology: str | None = None,
    execution_mode: str | None = None,
    created_at: datetime = auto,
    metadata: dict[str, Any] = {},
)
```

Back-compat convenience properties include:
- `pipeline_run_id`, `request_id`, `session_id`, `user_id`, `org_id`, `interaction_id`
- `messages -> list[Message]`
- `profile -> ProfileEnrichment | None`
- `memory -> MemoryEnrichment | None`
- `documents -> list[DocumentEnrichment]`
- `web_results -> list[dict[str, Any]]`

## Conversation

```python
from stageflow.context import Conversation
```

```python
Conversation(
    messages: list[Message] = [],
    routing_decision: RoutingDecision | None = None,
)
```

`Conversation` contains message/routing data only.
It does not define `input_text`, `input_audio_duration_ms`, or `metadata`.

## Enrichments

```python
from stageflow.context import Enrichments
```

```python
Enrichments(
    profile: ProfileEnrichment | None = None,
    memory: MemoryEnrichment | None = None,
    documents: list[DocumentEnrichment] = [],
    web_results: list[dict[str, Any]] = [],
)
```

## StageInputs

```python
from stageflow.stages.inputs import StageInputs, create_stage_inputs
```

Important APIs:
- `get(key, default=None)`
- `get_from(stage_name, key, default=None)`
- `require_from(stage_name, key)`
- `has_output(stage_name)`
- `get_output(stage_name)`
- `tool_registry` (property)

## StageContext

```python
from stageflow.api import StageContext
```

```python
StageContext(
    snapshot: ContextSnapshot,
    inputs: StageInputs,
    stage_name: str,
    timer: PipelineTimer,
    event_sink: EventSink | None = None,
)
```

`StageContext` is usually created internally by `UnifiedStageGraph`. Construct it
directly only in tests or advanced orchestration code.

Additional runtime properties:

- `is_cancelled: bool`
- `cancellation_reason: str | None`

Additional runtime methods:

- `raise_if_cancelled() -> None`
- `cancellation_checkpoint() -> Awaitable[None]`

`StageContext` uses these helpers for cooperative cancellation inside long-running
stages. The raised exception type is `StageCancellationRequested`.
