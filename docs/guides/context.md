# Context & Data Flow

Understanding how data flows through stageflow pipelines is essential for building effective applications. This guide covers the context system in depth.

## Context Overview

Stageflow uses a layered context system:

1. **ContextSnapshot** — Immutable input data for the entire pipeline
2. **StageContext** — Per-stage execution wrapper with output collection
3. **StageInputs** — Access to upstream stage outputs
4. **ContextBag** — Thread-safe output storage with conflict detection

```
┌─────────────────────────────────────────────────────────────┐
│                     ContextSnapshot                          │
│  (immutable: user_id, input_text, messages, enrichments)    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      StageContext                            │
│  (per-stage: snapshot access, config, output methods)       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      StageInputs                             │
│  (upstream outputs: get("key"), get_from("stage", "key"))   │
└─────────────────────────────────────────────────────────────┘
```

## ContextSnapshot

The `ContextSnapshot` is an **immutable**, **serializable** view of the world. It contains everything a stage needs to do its work.

### Creating a Snapshot

```python
from uuid import uuid4
from datetime import datetime
from stageflow.context import (
    ContextSnapshot,
    Message,
    RoutingDecision,
    ProfileEnrichment,
    MemoryEnrichment,
)

snapshot = ContextSnapshot(
    # Run Identity
    pipeline_run_id=uuid4(),
    request_id=uuid4(),
    session_id=uuid4(),
    user_id=uuid4(),
    org_id=uuid4(),
    interaction_id=uuid4(),
    
    # Configuration
    topology="chat_fast",
    execution_mode="practice",
    
    # Input
    input_text="Hello, how are you?",
    messages=[
        Message(role="user", content="Hi there", timestamp=datetime.utcnow()),
        Message(role="assistant", content="Hello!", timestamp=datetime.utcnow()),
    ],
    
    # Enrichments (optional, can be populated by stages)
    profile=ProfileEnrichment(
        user_id=uuid4(),
        display_name="Alice",
        preferences={"tone": "friendly"},
        goals=["learn Python"],
    ),
    memory=MemoryEnrichment(
        recent_topics=["programming", "AI"],
        key_facts=["prefers examples"],
    ),
    
    # Extensions (application-specific)
    extensions={"skills": {"active_skill_ids": ["python"]}},
    
    # Metadata
    metadata={"source": "web_chat"},
)
```

### Snapshot Fields

| Field | Type | Description |
|-------|------|-------------|
| `pipeline_run_id` | `UUID` | Unique identifier for this pipeline run |
| `request_id` | `UUID` | HTTP/WebSocket request identifier |
| `session_id` | `UUID` | User session identifier |
| `user_id` | `UUID` | User identifier |
| `org_id` | `UUID` | Organization/tenant identifier |
| `interaction_id` | `UUID` | Specific interaction identifier |
| `topology` | `str` | Pipeline topology name |
| `execution_mode` | `str` | Execution mode (practice, roleplay, etc.) |
| `input_text` | `str` | Raw user input |
| `messages` | `list[Message]` | Conversation history |
| `profile` | `ProfileEnrichment` | User profile data |
| `memory` | `MemoryEnrichment` | Conversation memory |
| `documents` | `list[DocumentEnrichment]` | Document context |
| `extensions` | `dict` | Application-specific data |
| `metadata` | `dict` | Additional metadata |

### Serialization

Snapshots can be serialized for testing, logging, or replay:

```python
# To dict
data = snapshot.to_dict()

# From dict
restored = ContextSnapshot.from_dict(data)
```

## StageContext

The `StageContext` wraps a snapshot and provides stage execution utilities.

### Accessing the Snapshot

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # All snapshot fields are accessible
    user_id = ctx.snapshot.user_id
    input_text = ctx.snapshot.input_text
    messages = ctx.snapshot.messages
    execution_mode = ctx.snapshot.execution_mode
```

### Accessing Configuration

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Stage configuration
    timeout = ctx.config.get("timeout", 30)
    model = ctx.config.get("model", "default")
    
    # Shared timer for consistent timing
    timer = ctx.timer
    elapsed = timer.elapsed_ms()
```

### Accessing Upstream Outputs

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    inputs = ctx.config.get("inputs")
    
    if inputs:
        # Get any key from upstream outputs
        processed_text = inputs.get("text")
        
        # Get from a specific stage
        route = inputs.get_from("router", "route", default="general")
        
        # Access snapshot through inputs
        user_id = inputs.snapshot.user_id
```

### Emitting Events

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Emit custom events
    ctx.emit_event("custom.started", {"step": 1})
    
    # Do work...
    
    ctx.emit_event("custom.completed", {"step": 1, "result": "success"})
    
    return StageOutput.ok(...)
```

### Adding Artifacts

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Add UI artifacts
    ctx.add_artifact(
        type="chart",
        payload={"data": [1, 2, 3], "title": "Results"},
    )
    
    return StageOutput.ok(artifact_added=True)
```

## Data Flow Between Stages

### How Outputs Flow

1. Stage A returns `StageOutput.ok(key="value")`
2. The framework collects the output
3. Stage B (depends on A) receives outputs via `inputs`

```python
# Stage A
class StageA:
    async def execute(self, ctx: StageContext) -> StageOutput:
        return StageOutput.ok(
            computed_value=42,
            metadata={"source": "stage_a"},
        )

# Stage B (depends on A)
class StageB:
    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs = ctx.config.get("inputs")
        
        # Access A's output
        value = inputs.get("computed_value")  # 42
        meta = inputs.get("metadata")  # {"source": "stage_a"}
        
        return StageOutput.ok(doubled=value * 2)
```

### Multiple Dependencies

When a stage depends on multiple upstream stages:

```python
# Stage C depends on both A and B
class StageC:
    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs = ctx.config.get("inputs")
        
        # Get from specific stages
        a_value = inputs.get_from("stage_a", "computed_value")
        b_value = inputs.get_from("stage_b", "doubled")
        
        # Or get any matching key (first found)
        any_value = inputs.get("computed_value")
        
        return StageOutput.ok(combined=a_value + b_value)
```

### Handling Missing Data

Always handle cases where upstream data might be missing:

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    inputs = ctx.config.get("inputs")
    
    # With default value
    value = inputs.get("optional_key", default="fallback") if inputs else "fallback"
    
    # Check before use
    if inputs and inputs.has("required_key"):
        data = inputs.get("required_key")
    else:
        return StageOutput.skip(reason="Missing required_key")
```

## ContextBag

The `ContextBag` provides thread-safe output storage with conflict detection. It's used internally by the framework but can be useful for advanced scenarios.

### Conflict Detection

The ContextBag prevents multiple stages from writing the same key:

```python
from stageflow.context import ContextBag, DataConflictError

bag = ContextBag()

# First write succeeds
await bag.write("key", "value1", "stage_a")

# Second write from different stage raises error
try:
    await bag.write("key", "value2", "stage_b")
except DataConflictError as e:
    print(f"Conflict: {e.key} written by {e.existing_writer}, "
          f"cannot write from {e.new_writer}")
```

### Reading Data

```python
# Read a value
value = bag.read("key", default=None)

# Check if key exists
if bag.has("key"):
    value = bag.read("key")

# Get all keys
keys = bag.keys()

# Get writer of a key
writer = bag.get_writer("key")  # "stage_a"
```

## Enrichments

Enrichments are structured data added to the context by ENRICH stages.

### ProfileEnrichment

User profile information:

```python
from stageflow.context import ProfileEnrichment

profile = ProfileEnrichment(
    user_id=uuid4(),
    display_name="Alice",
    preferences={"tone": "friendly", "language": "en"},
    goals=["learn Python", "build APIs"],
)
```

### MemoryEnrichment

Conversation memory:

```python
from stageflow.context import MemoryEnrichment

memory = MemoryEnrichment(
    recent_topics=["Python", "async programming"],
    key_facts=["prefers examples", "works at TechCorp"],
    interaction_history_summary="Discussed Python basics last session",
)
```

### DocumentEnrichment

Document context:

```python
from stageflow.context import DocumentEnrichment

document = DocumentEnrichment(
    document_id="doc_123",
    document_type="sales_script",
    blocks=[
        {"id": "blk_1", "type": "heading", "content": "Introduction"},
        {"id": "blk_2", "type": "paragraph", "content": "Welcome..."},
    ],
    metadata={"version": 3, "last_edited": "2024-01-15"},
)
```

## Extensions

Extensions allow applications to add custom data to the context without modifying core types.

### Using Extensions

```python
# Add extension data to snapshot
snapshot = ContextSnapshot(
    ...,
    extensions={
        "skills": {
            "active_skill_ids": ["python", "javascript"],
            "current_level": "intermediate",
        },
        "custom_app_data": {
            "feature_flags": ["new_ui", "beta_features"],
        },
    },
)

# Access in stage
async def execute(self, ctx: StageContext) -> StageOutput:
    skills = ctx.snapshot.extensions.get("skills", {})
    active_skills = skills.get("active_skill_ids", [])
```

### Typed Extensions

For type safety, use the extension registry:

```python
from dataclasses import dataclass, field
from stageflow.extensions import ExtensionRegistry, ExtensionHelper

@dataclass
class SkillsExtension:
    active_skill_ids: list[str] = field(default_factory=list)
    current_level: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "SkillsExtension":
        return cls(
            active_skill_ids=data.get("active_skill_ids", []),
            current_level=data.get("current_level"),
        )

# Register
ExtensionRegistry.register("skills", SkillsExtension)

# Use with type safety
skills = ExtensionHelper.get(
    ctx.snapshot.extensions,
    "skills",
    SkillsExtension,
)
if skills:
    print(skills.active_skill_ids)  # IDE knows this is list[str]
```

## Message History

The `messages` field contains conversation history:

```python
from stageflow.context import Message

messages = [
    Message(
        role="system",
        content="You are a helpful assistant.",
        timestamp=datetime.utcnow(),
        metadata={"source": "config"},
    ),
    Message(
        role="user",
        content="Hello!",
        timestamp=datetime.utcnow(),
    ),
    Message(
        role="assistant",
        content="Hi there! How can I help?",
        timestamp=datetime.utcnow(),
        metadata={"model": "gpt-4"},
    ),
]
```

### Accessing Messages in Stages

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    messages = ctx.snapshot.messages
    
    # Get last N messages
    recent = messages[-5:]
    
    # Filter by role
    user_messages = [m for m in messages if m.role == "user"]
    
    # Convert for LLM
    llm_messages = [
        {"role": m.role, "content": m.content}
        for m in messages
    ]
```

## Routing Decisions

The `routing_decision` field captures routing stage output:

```python
from stageflow.context import RoutingDecision

decision = RoutingDecision(
    agent_id="support_agent",
    pipeline_name="support_pipeline",
    topology="support_fast",
    reason="User asked for help with billing",
)
```

## Best Practices

### 1. Keep Snapshots Immutable

Never try to modify a snapshot. Create new data in stage outputs:

```python
# Bad: Trying to modify snapshot
ctx.snapshot.input_text = "modified"  # This will fail!

# Good: Return new data in output
return StageOutput.ok(processed_text="modified")
```

### 2. Use Descriptive Output Keys

Choose clear, descriptive keys for stage outputs:

```python
# Good
return StageOutput.ok(
    user_profile=profile,
    profile_fetch_duration_ms=elapsed,
)

# Bad
return StageOutput.ok(
    p=profile,
    d=elapsed,
)
```

### 3. Handle Missing Data Gracefully

Always provide defaults or skip when data is missing:

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    user_id = ctx.snapshot.user_id
    if not user_id:
        return StageOutput.skip(reason="No user_id provided")
    
    # Continue with valid data...
```

### 4. Document Expected Inputs/Outputs

Make it clear what your stage expects and produces:

```python
class MyStage:
    """Process user input.
    
    Inputs:
        - snapshot.input_text: Raw user input
        - upstream.validated: Boolean from guard stage
    
    Outputs:
        - processed_text: Transformed text
        - word_count: Number of words
    """
```

## Next Steps

- [Interceptors](interceptors.md) — Add middleware for cross-cutting concerns
- [Tools & Agents](tools.md) — Build agent capabilities
- [Examples](../examples/parallel.md) — See data flow in action
