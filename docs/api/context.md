# Context API Reference

## RunIdentity

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

## ContextSnapshot

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
from stageflow.core import StageContext
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
