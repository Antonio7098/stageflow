# Context API Reference

This document provides the API reference for context types and data flow.

## ContextSnapshot

```python
from stageflow.context import ContextSnapshot
```

Immutable view passed to stages containing run identity, messages, enrichments, and routing decision.

### Constructor

```python
ContextSnapshot(
    pipeline_run_id: UUID | None,
    request_id: UUID | None,
    session_id: UUID | None,
    user_id: UUID | None,
    org_id: UUID | None,
    interaction_id: UUID | None,
    topology: str | None = None,
    execution_mode: str | None = None,
    messages: list[Message] = [],
    routing_decision: RoutingDecision | None = None,
    profile: ProfileEnrichment | None = None,
    memory: MemoryEnrichment | None = None,
    documents: list[DocumentEnrichment] = [],
    web_results: list[dict] = [],
    input_text: str | None = None,
    input_audio_duration_ms: int | None = None,
    extensions: dict[str, Any] = {},
    metadata: dict[str, Any] = {},
)
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `pipeline_run_id` | `UUID \| None` | Pipeline run identifier |
| `request_id` | `UUID \| None` | Request identifier |
| `session_id` | `UUID \| None` | Session identifier |
| `user_id` | `UUID \| None` | User identifier |
| `org_id` | `UUID \| None` | Organization identifier |
| `interaction_id` | `UUID \| None` | Interaction identifier |
| `topology` | `str \| None` | Pipeline topology name |
| `execution_mode` | `str \| None` | Execution mode |
| `messages` | `list[Message]` | Conversation history |
| `routing_decision` | `RoutingDecision \| None` | Routing decision |
| `profile` | `ProfileEnrichment \| None` | User profile |
| `memory` | `MemoryEnrichment \| None` | Conversation memory |
| `documents` | `list[DocumentEnrichment]` | Document context |
| `web_results` | `list[dict]` | Web search results |
| `input_text` | `str \| None` | Raw user input |
| `input_audio_duration_ms` | `int \| None` | Audio duration |
| `extensions` | `dict[str, Any]` | Application-specific data |
| `created_at` | `datetime` | Creation timestamp |
| `metadata` | `dict[str, Any]` | Additional metadata |

### Methods

#### `to_dict() -> dict[str, Any]`

Convert to JSON-serializable dict.

#### `from_dict(data: dict) -> ContextSnapshot` (classmethod)

Create from JSON dict.

```python
data = snapshot.to_dict()
restored = ContextSnapshot.from_dict(data)
```

---

## Message

```python
from stageflow.context import Message
```

A single message in the conversation history.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `role` | `str` | Message role ("user", "assistant", "system") |
| `content` | `str` | Message content |
| `timestamp` | `datetime \| None` | When message was sent |
| `metadata` | `dict[str, Any]` | Additional metadata |

```python
from stageflow.context import Message
from datetime import datetime

msg = Message(
    role="user",
    content="Hello!",
    timestamp=datetime.utcnow(),
    metadata={"source": "web"},
)
```

---

## RoutingDecision

```python
from stageflow.context import RoutingDecision
```

Routing decision made by a router stage.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `agent_id` | `str` | Selected agent identifier |
| `pipeline_name` | `str` | Target pipeline name |
| `topology` | `str` | Target topology |
| `reason` | `str \| None` | Routing reason |

```python
from stageflow.context import RoutingDecision

decision = RoutingDecision(
    agent_id="support_agent",
    pipeline_name="support_pipeline",
    topology="support_fast",
    reason="User asked for help",
)
```

---

## ProfileEnrichment

```python
from stageflow.context import ProfileEnrichment
```

User profile enrichment data.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `user_id` | `UUID` | User identifier |
| `display_name` | `str \| None` | Display name |
| `preferences` | `dict[str, Any]` | User preferences |
| `goals` | `list[str]` | User goals |

```python
from stageflow.context import ProfileEnrichment

profile = ProfileEnrichment(
    user_id=uuid4(),
    display_name="Alice",
    preferences={"tone": "friendly"},
    goals=["Learn Python"],
)
```

---

## MemoryEnrichment

```python
from stageflow.context import MemoryEnrichment
```

Conversation memory enrichment data.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `recent_topics` | `list[str]` | Recent discussion topics |
| `key_facts` | `list[str]` | Key facts about user |
| `interaction_history_summary` | `str \| None` | History summary |

```python
from stageflow.context import MemoryEnrichment

memory = MemoryEnrichment(
    recent_topics=["Python", "async"],
    key_facts=["prefers examples"],
    interaction_history_summary="Discussed basics last session",
)
```

---

## DocumentEnrichment

```python
from stageflow.context import DocumentEnrichment
```

Document context enrichment data.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `document_id` | `str \| None` | Document identifier |
| `document_type` | `str \| None` | Document type |
| `blocks` | `list[dict]` | Document blocks |
| `metadata` | `dict[str, Any]` | Document metadata |

```python
from stageflow.context import DocumentEnrichment

doc = DocumentEnrichment(
    document_id="doc_123",
    document_type="sales_script",
    blocks=[{"id": "blk_1", "type": "paragraph", "content": "..."}],
    metadata={"version": 3},
)
```

---

## ContextBag

```python
from stageflow.context import ContextBag, DataConflictError
```

Thread-safe output storage with conflict detection.

### Methods

#### `write(key: str, value: Any, stage_name: str) -> None`

Write a key-value pair, rejecting duplicates.

**Raises:** `DataConflictError` if key was already written by another stage

```python
bag = ContextBag()
await bag.write("result", "value", "my_stage")
```

#### `read(key: str, default=None) -> Any`

Read a value (no lock needed).

```python
value = bag.read("result", default="fallback")
```

#### `has(key: str) -> bool`

Check if a key exists.

#### `keys() -> list[str]`

Get all stored keys.

#### `get_writer(key: str) -> str | None`

Get the stage that wrote a specific key.

#### `to_dict() -> dict[str, Any]`

Convert bag contents to a dictionary.

### DataConflictError

```python
from stageflow.context import DataConflictError
```

Raised when multiple stages attempt to write the same key.

**Attributes:**
- `key`: `str` — The conflicting key
- `existing_writer`: `str` — Stage that first wrote the key
- `new_writer`: `str` — Stage attempting to overwrite

```python
try:
    await bag.write("key", "value", "stage_b")
except DataConflictError as e:
    print(f"Key '{e.key}' already written by '{e.existing_writer}'")
```

---

## PipelineContext

```python
from stageflow.stages.context import PipelineContext
```

Execution context shared between stages (used by StageGraph internally).

### Attributes

| Attribute        | Type                    | Description                                  |
|------------------|-------------------------|----------------------------------------------|
| `pipeline_run_id` | `UUID \| None`        | Pipeline run identifier                      |
| `request_id`    | `UUID \| None`          | Request identifier                           |
| `session_id`    | `UUID \| None`          | Session identifier                           |
| `user_id`       | `UUID \| None`          | User identifier                              |
| `org_id`        | `UUID \| None`          | Organization identifier                      |
| `interaction_id` | `UUID \| None`         | Interaction identifier                       |
| `topology`      | `str \| None`           | Pipeline topology name                       |
| `configuration` | `dict[str, Any]`        | Static configuration for this topology       |
| `execution_mode`| `str \| None`           | Execution mode (e.g. `"practice"`)          |
| `service`       | `str`                   | Logical service name (e.g. `"pipeline"`)    |
| `event_sink`    | `EventSink`             | Sink used for emitting events                |
| `data`          | `dict[str, Any]`        | Shared data dictionary across stages         |
| `db`            | `Any`                   | Database/session handle (implementation-dependent) |
| `canceled`      | `bool`                  | Cancellation flag                            |
| `artifacts`     | `list[Artifact]`        | Produced artifacts                           |
| `_stage_metadata` | `dict[str, dict]`     | Per-stage observability metadata             |
| `parent_run_id` | `UUID \| None`          | Parent pipeline run ID (for subpipelines)    |
| `parent_stage_id` | `str \| None`        | Name of stage that spawned this child run    |
| `correlation_id` | `UUID \| None`        | Correlation/action ID that triggered child   |
| `_parent_data`  | `FrozenDict[str, Any] \| None` | Read-only snapshot of parent `data`   |

### Methods

#### `record_stage_event(stage, status, payload=None) -> None`

Emit a timestamped stage event enriched with run identity and configuration.

#### `set_stage_metadata(stage: str, metadata: dict[str, Any]) -> None`

Store per-stage metadata for observability/analytics.

#### `get_stage_metadata(stage: str) -> dict[str, Any] | None`

Retrieve previously stored metadata for a stage.

#### `to_dict() -> dict[str, Any]`

Convert context to a dict suitable for tool execution and logging.

#### `fork(child_run_id, parent_stage_id, correlation_id, *, topology=None, execution_mode=None) -> PipelineContext`

Create a child context for a subpipeline run:

- New `pipeline_run_id` (child_run_id)
- Inherits auth fields and configuration
- Fresh `data` and `artifacts`
- `parent_run_id`, `parent_stage_id`, `correlation_id` set
- `_parent_data` is a frozen copy of the parent `data`

#### `mark_canceled() -> None`

Mark this context as canceled.

#### `is_canceled -> bool` (property)

Check if this context has been canceled.

#### `try_emit_event(type: str, data: dict[str, Any]) -> None`

Emit an event via the `event_sink` (non-blocking) with run-level enrichment.

#### `now() -> datetime` (classmethod)

Return current UTC timestamp for consistent timing.

---

## StageInputs

```python
from stageflow.stages.inputs import StageInputs, create_stage_inputs
```

Immutable view of prior stage outputs available to a stage. This is the canonical input type for stages following the immutable data flow pattern.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `snapshot` | `ContextSnapshot` | Original immutable snapshot (run identity, messages, etc.) |
| `prior_outputs` | `dict[str, StageOutput]` | Outputs from declared dependency stages only |
| `ports` | `StagePorts` | Injected capabilities (db, callbacks, services) |

### Methods

#### `get(key: str, default=None) -> Any`

Get a value from any prior stage's output data. Searches through all `prior_outputs` in insertion order.

```python
inputs = ctx.config.get("inputs")
transcript = inputs.get("transcript")  # First match from any stage
```

#### `get_from(stage_name: str, key: str, default=None) -> Any`

Get a specific value from a specific stage's output. Preferred method for explicit dependencies.

```python
route = inputs.get_from("router", "route", default="general")
```

#### `has_output(stage_name: str) -> bool`

Check if a stage has produced output.

#### `get_output(stage_name: str) -> StageOutput | None`

Get a stage's complete `StageOutput` object.

### Factory Function

```python
from stageflow.stages.inputs import create_stage_inputs

inputs = create_stage_inputs(
    snapshot=snapshot,
    prior_outputs={"stage_a": stage_a_output},
    ports=my_ports,
)
```

---

## Modular Ports

Stageflow provides modular ports following the Interface Segregation Principle. Stages only receive the ports they need.

### CorePorts

```python
from stageflow.stages.ports import CorePorts, create_core_ports
```

Essential capabilities needed by most stages.

**Attributes:**
| Attribute | Type | Description |
|-----------|------|-------------|
| `db` | `Any` | Database session for persistence operations |
| `db_lock` | `Lock \| None` | Optional lock for preventing concurrent DB access |
| `call_logger_db` | `Any` | Database session for provider call logging |
| `send_status` | `Callable` | Callback for sending status updates |
| `call_logger` | `Any` | Logger for tracking provider API calls |
| `retry_fn` | `Any` | Retry function for failed operations |

```python
ports = create_core_ports(
    db=my_db_session,
    send_status=my_status_callback,
)
```

### LLMPorts

```python
from stageflow.stages.ports import LLMPorts, create_llm_ports
```

Ports for LLM-powered stages.

**Attributes:**
| Attribute | Type | Description |
|-----------|------|-------------|
| `llm_provider` | `Any` | LLM provider for text generation |
| `chat_service` | `Any` | Chat service for building context |
| `llm_chunk_queue` | `Any` | Queue for LLM chunks in streaming |
| `send_token` | `Callable` | Callback for streaming tokens |

```python
ports = create_llm_ports(
    llm_provider=my_llm,
    send_token=token_callback,
)
```

### AudioPorts

```python
from stageflow.stages.ports import AudioPorts, create_audio_ports
```

Ports for audio processing stages.

**Attributes:**
| Attribute | Type | Description |
|-----------|------|-------------|
| `tts_provider` | `Any` | TTS provider for text-to-speech |
| `stt_provider` | `Any` | STT provider for speech-to-text |
| `send_audio_chunk` | `Callable` | Callback for streaming audio |
| `send_transcript` | `Callable` | Callback for sending transcript |
| `audio_data` | `bytes \| None` | Raw audio bytes |
| `audio_format` | `str \| None` | Audio format |
| `tts_text_queue` | `Any` | Queue for text to synthesize |
| `recording` | `Any` | Recording metadata |

```python
ports = create_audio_ports(
    tts_provider=my_tts,
    stt_provider=my_stt,
    send_audio_chunk=audio_callback,
)
```


---

## Usage Example

```python
from uuid import uuid4
from datetime import datetime
from stageflow.context import (
    ContextSnapshot,
    Message,
    RoutingDecision,
    ProfileEnrichment,
    MemoryEnrichment,
    ContextBag,
)

# Create a full context snapshot
snapshot = ContextSnapshot(
    pipeline_run_id=uuid4(),
    request_id=uuid4(),
    session_id=uuid4(),
    user_id=uuid4(),
    org_id=uuid4(),
    interaction_id=uuid4(),
    topology="chat_fast",
    execution_mode="practice",
    input_text="Hello!",
    messages=[
        Message(role="user", content="Hi", timestamp=datetime.utcnow()),
        Message(role="assistant", content="Hello!", timestamp=datetime.utcnow()),
    ],
    profile=ProfileEnrichment(
        user_id=uuid4(),
        display_name="Alice",
        preferences={"tone": "friendly"},
        goals=["Learn Python"],
    ),
    memory=MemoryEnrichment(
        recent_topics=["async programming"],
        key_facts=["prefers examples"],
    ),
    extensions={"custom": {"key": "value"}},
)

# Serialize and restore
data = snapshot.to_dict()
restored = ContextSnapshot.from_dict(data)

# Use ContextBag for parallel stage outputs
bag = ContextBag()
await bag.write("profile", {"name": "Alice"}, "profile_stage")
await bag.write("memory", {"topics": ["Python"]}, "memory_stage")

profile = bag.read("profile")
all_keys = bag.keys()
```
