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

| Attribute | Type | Description |
|-----------|------|-------------|
| `pipeline_run_id` | `UUID \| None` | Pipeline run identifier |
| `request_id` | `UUID \| None` | Request identifier |
| `session_id` | `UUID \| None` | Session identifier |
| `user_id` | `UUID \| None` | User identifier |
| `org_id` | `UUID \| None` | Organization identifier |
| `topology` | `str \| None` | Pipeline topology |
| `execution_mode` | `str \| None` | Execution mode |
| `data` | `dict[str, Any]` | Shared data dictionary |
| `canceled` | `bool` | Cancellation flag |
| `artifacts` | `list[Artifact]` | Produced artifacts |

### Methods

#### `record_stage_event(stage, status, payload=None) -> None`

Emit a timestamped stage event.

#### `fork(child_run_id, parent_stage_id, correlation_id, ...) -> PipelineContext`

Create a child context for a subpipeline run.

#### `mark_canceled() -> None`

Mark this context as canceled.

#### `to_dict() -> dict[str, Any]`

Convert context to dict.

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
