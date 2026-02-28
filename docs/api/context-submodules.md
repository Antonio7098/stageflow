# Context Sub-modules API Reference

This page documents the concrete APIs in `stageflow.context`.

## Exports

```python
from stageflow.context import (
    ContextBag,
    ContextSnapshot,
    Conversation,
    DataConflictError,
    DocumentEnrichment,
    Enrichments,
    ExtensionBundle,
    MemoryEnrichment,
    OutputBag,
    OutputConflictError,
    OutputEntry,
    ProfileEnrichment,
    RunIdentity,
)
```

## ExtensionBundle

Use `ExtensionBundle` as the typed base for custom extension data.

```python
from dataclasses import dataclass
from stageflow.context import ExtensionBundle

@dataclass(frozen=True)
class UserExtensions(ExtensionBundle):
    locale: str = "en"
    plan: str = "free"
```

## ProfileEnrichment

```python
ProfileEnrichment(
    user_id: UUID | None = None,
    display_name: str | None = None,
    preferences: dict[str, Any] = {},
    goals: list[str] = [],
)
```

## RunIdentity

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

## OutputBag

`OutputBag` is append-only with explicit overwrite for retries.

```python
from stageflow.context import OutputBag
from stageflow import StageOutput

bag = OutputBag()
entry = await bag.write("stage_a", StageOutput.ok(result="ok"))
entry2 = await bag.write("stage_a", StageOutput.ok(result="retry"), allow_overwrite=True)
```

### Key methods

- `async write(stage_name, output, *, allow_overwrite=False) -> OutputEntry`
- `write_sync(stage_name, output, *, allow_overwrite=False) -> OutputEntry`
- `get(stage_name) -> OutputEntry | None`
- `get_output(stage_name) -> StageOutput | None`
- `get_value(stage_name, key, default=None) -> Any`
- `has(stage_name) -> bool`
- `keys() -> list[str]`
- `entries() -> list[OutputEntry]`
- `outputs() -> dict[str, StageOutput]`
- `to_dict() -> dict[str, Any]`

## Conversation

```python
Conversation(
    messages: list[Message] = [],
    routing_decision: RoutingDecision | None = None,
)
```

`Conversation` has `messages` and `routing_decision` (plus derived properties like `last_user_message`).
It does not define `input_text`, `input_audio_duration_ms`, or `metadata`.

## ContextBag (legacy)

`ContextBag` remains available for compatibility; new code should prefer `OutputBag`.
