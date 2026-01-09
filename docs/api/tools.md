# Tools API Reference

This document provides the API reference for the tool execution system.

## Tool Protocol

```python
from stageflow.tools import Tool
```

Protocol for self-describing capability units.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Unique tool identifier |
| `description` | `str` | Human-readable description |
| `action_type` | `str` | Action type this tool handles |

### Methods

#### `execute(input: ToolInput, ctx: dict) -> ToolOutput`

Execute the tool.

**Parameters:**
- `input`: `ToolInput` — Wrapped action with context
- `ctx`: `dict` — Pipeline context as dictionary

**Returns:** `ToolOutput` with success status and data

---

## BaseTool

```python
from stageflow.tools import BaseTool
```

Base class for implementing tools.

```python
class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    action_type = "MY_ACTION"
    
    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        return ToolOutput(success=True, data={"result": "done"})
```

---

## ToolInput

```python
from stageflow.tools import ToolInput
```

Input schema for a tool.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `action_id` | `UUID` | Unique action identifier |
| `tool_name` | `str` | Name of the tool |
| `payload` | `dict[str, Any]` | Action payload data |
| `behavior` | `str \| None` | Current execution mode |
| `pipeline_run_id` | `UUID \| None` | Pipeline run ID |
| `request_id` | `UUID \| None` | Request ID |

### Class Methods

#### `from_action(action, tool_name, ctx=None) -> ToolInput`

Create ToolInput from an Action and context.

```python
tool_input = ToolInput.from_action(action, "my_tool", ctx)
```

---

## ToolOutput

```python
from stageflow.tools import ToolOutput
```

Output from tool execution.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `success` | `bool` | Whether execution succeeded |
| `data` | `dict \| None` | Output data |
| `error` | `str \| None` | Error message if failed |
| `artifacts` | `list[dict] \| None` | Produced artifacts |
| `undo_metadata` | `dict \| None` | Data for undoing action |

### Class Methods

#### `ok(data=None, artifacts=None, undo_metadata=None) -> ToolOutput`

Create a successful output.

```python
return ToolOutput.ok(data={"result": "done"})
```

#### `fail(error: str) -> ToolOutput`

Create a failed output.

```python
return ToolOutput.fail("Something went wrong")
```

---

## ToolDefinition

```python
from stageflow.tools import ToolDefinition
```

Enhanced tool definition with gating, undo, and approval.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Tool identifier |
| `action_type` | `str` | Action type handled |
| `handler` | `ToolHandler` | Async execution function |
| `description` | `str` | Tool description |
| `input_schema` | `dict` | JSON Schema for input |
| `allowed_behaviors` | `tuple[str, ...]` | Allowed execution modes |
| `requires_approval` | `bool` | Needs HITL approval |
| `approval_message` | `str \| None` | Approval UI message |
| `undoable` | `bool` | Can be undone |
| `undo_handler` | `UndoHandler \| None` | Undo function |
| `artifact_type` | `str \| None` | Artifact type produced |

### Methods

#### `is_behavior_allowed(behavior: str | None) -> bool`

Check if behavior can use this tool.

```python
if tool.is_behavior_allowed(ctx.execution_mode):
    result = await tool.handler(input)
```

---

## Action Protocol

```python
from stageflow.tools import Action
```

Protocol for action objects.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | `UUID` | Unique action identifier |
| `type` | `str` | Action type string |
| `payload` | `dict[str, Any]` | Action payload |

---

## ToolRegistry

```python
from stageflow.tools import ToolRegistry, get_tool_registry
```

Registry for tool discovery and execution.

### Methods

#### `register(tool: Tool) -> None`

Register a tool instance.

```python
registry = get_tool_registry()
registry.register(MyTool())
```

#### `get(name: str) -> Tool | None`

Get tool by name.

#### `get_by_action_type(action_type: str) -> Tool | None`

Get tool by action type.

#### `list() -> list[Tool]`

List all registered tools.

#### `has(name: str) -> bool`

Check if tool is registered.

#### `execute(action, ctx: dict) -> ToolOutput`

Execute a tool for an action.

```python
result = await registry.execute(action, ctx)
```

### Decorator

```python
from stageflow.tools import register_tool

@register_tool
class MyTool(BaseTool):
    name = "my_tool"
    ...
```

---

## ToolExecutor

```python
from stageflow.tools import ToolExecutor
```

Basic tool executor.

### Methods

#### `execute(action, ctx: dict) -> ToolOutput`

Execute a tool for an action.

---

## AdvancedToolExecutor

```python
from stageflow.tools import AdvancedToolExecutor, ToolExecutorConfig, ExecutionResult
```

Advanced executor with observability and behavior gating.

### ToolExecutorConfig

| Attribute | Type | Description |
|-----------|------|-------------|
| `emit_events` | `bool` | Emit tool events |
| `store_undo_data` | `bool` | Store undo metadata |
| `require_approval_for_risky` | `bool` | Require HITL approval |

### ExecutionResult

| Attribute | Type | Description |
|-----------|------|-------------|
| `success` | `bool` | Execution succeeded |
| `output` | `ToolOutput` | Tool output |
| `events` | `list` | Emitted events |

---

## UndoMetadata

```python
from stageflow.tools import UndoMetadata
```

Metadata for undoable actions.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `action_id` | `UUID` | Action identifier |
| `tool_name` | `str` | Tool name |
| `undo_data` | `dict` | Data for undo |
| `created_at` | `str` | Creation timestamp |

---

## UndoStore

```python
from stageflow.tools import UndoStore, get_undo_store, set_undo_store
```

Storage for undo metadata.

### Methods

#### `store(metadata: UndoMetadata) -> None`

Store undo metadata.

#### `get(action_id: UUID) -> UndoMetadata | None`

Retrieve undo metadata.

#### `remove(action_id: UUID) -> None`

Remove undo metadata.

---

## ApprovalService

```python
from stageflow.tools import (
    ApprovalService,
    ApprovalRequest,
    ApprovalDecision,
    ApprovalStatus,
    get_approval_service,
)
```

Service for HITL approval flows.

### ApprovalStatus

| Value | Description |
|-------|-------------|
| `PENDING` | Awaiting decision |
| `APPROVED` | User approved |
| `DENIED` | User denied |
| `EXPIRED` | Request expired |

### ApprovalRequest

| Attribute | Type | Description |
|-----------|------|-------------|
| `action_id` | `UUID` | Action identifier |
| `tool_name` | `str` | Tool name |
| `message` | `str` | Approval message |
| `payload` | `dict` | Action payload |

### Methods

#### `request(request: ApprovalRequest) -> None`

Request approval.

#### `get_status(action_id: UUID) -> ApprovalStatus`

Get approval status.

#### `decide(action_id: UUID, decision: ApprovalDecision) -> None`

Record approval decision.

---

## Errors

```python
from stageflow.tools import (
    ToolError,
    ToolNotFoundError,
    ToolDeniedError,
    ToolExecutionError,
    ToolApprovalDeniedError,
    ToolApprovalTimeoutError,
    ToolUndoError,
)
```

| Error | Description |
|-------|-------------|
| `ToolError` | Base tool error |
| `ToolNotFoundError` | Tool not registered |
| `ToolDeniedError` | Tool denied (behavior gating) |
| `ToolExecutionError` | Execution failed |
| `ToolApprovalDeniedError` | Approval denied |
| `ToolApprovalTimeoutError` | Approval timed out |
| `ToolUndoError` | Undo operation failed |

---

## Events

```python
from stageflow.tools import (
    ToolInvokedEvent,
    ToolStartedEvent,
    ToolCompletedEvent,
    ToolFailedEvent,
    ToolDeniedEvent,
    ToolUndoneEvent,
    ToolUndoFailedEvent,
)
```

Tool execution events for observability.

---

## Usage Example

```python
from uuid import uuid4
from dataclasses import dataclass
from stageflow.tools import (
    BaseTool,
    ToolInput,
    ToolOutput,
    ToolDefinition,
    get_tool_registry,
    register_tool,
)

# Simple tool using BaseTool
@register_tool
class GreetTool(BaseTool):
    name = "greet"
    description = "Greet a user"
    action_type = "GREET"
    
    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        name = input.action.payload.get("name", "World")
        return ToolOutput.ok(data={"message": f"Hello, {name}!"})

# Advanced tool with undo
async def edit_handler(input: ToolInput) -> ToolOutput:
    doc_id = input.payload["document_id"]
    content = input.payload["content"]
    original = get_document(doc_id)
    set_document(doc_id, content)
    return ToolOutput.ok(
        data={"updated": True},
        undo_metadata={"doc_id": doc_id, "original": original},
    )

async def edit_undo(metadata):
    set_document(metadata.undo_data["doc_id"], metadata.undo_data["original"])

edit_tool = ToolDefinition(
    name="edit_document",
    action_type="EDIT_DOCUMENT",
    handler=edit_handler,
    undoable=True,
    undo_handler=edit_undo,
    requires_approval=True,
    allowed_behaviors=("doc_edit",),
)

# Execute tools
@dataclass
class Action:
    id: uuid4
    type: str
    payload: dict

registry = get_tool_registry()
action = Action(id=uuid4(), type="GREET", payload={"name": "Alice"})
result = await registry.execute(action, ctx={})
print(result.data)  # {"message": "Hello, Alice!"}
```
