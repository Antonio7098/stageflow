# STF-SPR-003: Advanced ToolExecutor

**Status:** 🔴 Not Started  
**Branch:** `feature/stf-spr-003-advanced-tool-executor`  
**Duration:** 1 week  
**Dependencies:** STF-SPR-001 (Pipeline Composition), STF-SPR-002 (Auth Interceptors)

---

## 📅 Sprint Details & Goals

### Overview
Upgrade ToolExecutor to support behavior gating, undo semantics, HITL approval flows, and comprehensive tool telemetry for the stageflow framework.

### Primary Goal (Must-Have)
- **Tools are gated by behavior (e.g., `doc_edit` behavior enables EDIT_DOCUMENT tool)**
- **Tools emit full `tool.*` event lifecycle**
- **Undo semantics allow reversing tool actions**
- **HITL approval flow for risky actions**

### Success Criteria
- [ ] ToolExecutor checks behavior gating before execution
- [ ] All tool executions emit `tool.invoked`, `tool.started`, `tool.completed|failed`
- [ ] Undo metadata stored for reversible actions
- [ ] `tool.undone` event emitted on undo
- [ ] HITL approval flow for risky tools
- [ ] Integration tests for gating, undo, approval pass

---

## 🏗️ Architecture & Design

### Tool Definition Schema

```python
@dataclass(frozen=True)
class ToolDefinition:
    """Definition of a tool capability."""
    name: str
    input_schema: dict[str, Any]  # JSON Schema
    handler: Callable[[ToolInput], Awaitable[ToolOutput]]
    
    # Behavior gating
    allowed_behaviors: tuple[str, ...] = ()  # Empty = all behaviors
    
    # Policy
    requires_approval: bool = False
    approval_message: str | None = None
    
    # Undo semantics
    undoable: bool = False
    undo_handler: Callable[[ToolOutput], Awaitable[None]] | None = None
    
    # Artifact behavior
    artifact_type: str | None = None
```

### Behavior Gating

```python
class ToolExecutor:
    async def execute(self, action: Action, ctx: PipelineContext) -> ToolOutput:
        tool = self.registry.get(action.type)
        
        # Check behavior gating
        if tool.allowed_behaviors:
            current_behavior = ctx.behavior
            if current_behavior not in tool.allowed_behaviors:
                await self._emit_tool_denied(action, ctx, reason="behavior_not_allowed")
                raise ToolDeniedError(
                    tool=action.type,
                    behavior=current_behavior,
                    allowed=tool.allowed_behaviors,
                )
        
        # Check HITL approval if required
        if tool.requires_approval:
            approval = await self._request_approval(action, ctx, tool)
            if not approval.granted:
                await self._emit_tool_denied(action, ctx, reason="approval_denied")
                raise ToolApprovalDeniedError(tool=action.type)
        
        # Execute with full telemetry
        await self._emit_tool_invoked(action, ctx)
        try:
            await self._emit_tool_started(action, ctx)
            output = await tool.handler(ToolInput.from_action(action))
            await self._emit_tool_completed(action, ctx, output)
            
            # Store undo metadata if undoable
            if tool.undoable and output.success:
                await self._store_undo_metadata(action, ctx, output)
            
            return output
        except Exception as e:
            await self._emit_tool_failed(action, ctx, e)
            raise
```

### Tool Event Lifecycle

```
tool.invoked    → Action received, tool lookup complete
tool.started    → Execution beginning
tool.completed  → Success, output available
tool.failed     → Error during execution
tool.undone     → Action reversed via undo
tool.undo_failed → Undo attempt failed
```

### HITL Approval Flow

```
Agent plans risky action
    │
    ├── ToolExecutor detects requires_approval=True
    │
    ├── Emit `approval.requested` event
    │
    ├── Create `approval_requests` DB row
    │
    ├── Projector sends approval UI artifact to client
    │
    ├── User approves/denies via WebSocket
    │
    ├── ToolExecutor receives approval decision
    │
    └── Continue or abort based on decision
```

---

## 🧩 Parallelization Plan (A/B/C)

### Worker A (Behavior Gating)
**Owns:** Tool capability definitions and gating logic

- **Task 1.1:** Create `ToolDefinition` with `allowed_behaviors`
- **Task 1.2:** Implement behavior gating in ToolExecutor
- **Task 1.3:** Update tool registry with behavior metadata
- **Task 1.4:** Unit tests for gating scenarios

### Worker B (Telemetry + Undo)
**Owns:** Tool events and undo semantics

- **Task 2.1:** Implement full `tool.*` event emission
- **Task 2.2:** Create undo metadata storage
- **Task 2.3:** Implement `undo_action()` method
- **Task 2.4:** Unit tests for undo flow

### Worker C (HITL Approval)
**Owns:** Approval request flow

- **Task 3.1:** Create `approval_requests` table
- **Task 3.2:** Implement approval request/response flow
- **Task 3.3:** Create approval UI artifact
- **Task 3.4:** Integration tests for approval flow

### Gates

- **G7 (Advanced ToolExecutor):**
  - [ ] Worker A: Behavior gating implemented
  - [ ] Worker B: Tool events + undo working
  - [ ] Worker C: HITL approval flow working

---

## ✅ Detailed Task List

### Setup & Infrastructure
- [ ] **Task 0.1: Review existing ToolExecutor**
  - [ ] Read `stageflow/tools/executor.py` to understand current implementation
  - [ ] Identify existing tool registration patterns
  - [ ] Document current tool execution flow

- [ ] **Task 0.2: Create tools module structure**
  - [ ] Verify `stageflow/tools/` directory exists
  - [ ] Create `stageflow/tools/definitions.py` for ToolDefinition
  - [ ] Create `stageflow/tools/errors.py` for tool exceptions
  - [ ] Create `stageflow/tools/undo.py` for undo logic

### ToolDefinition Enhancement (Worker A)
- [ ] **Task 1.1: Update ToolDefinition dataclass**
  - [ ] Update `stageflow/tools/definitions.py`
  - [ ] Add `allowed_behaviors: tuple[str, ...] = ()` field (empty = all behaviors allowed)
  - [ ] Add `requires_approval: bool = False` field
  - [ ] Add `approval_message: str | None = None` field
  - [ ] Add `undoable: bool = False` field
  - [ ] Add `undo_handler: Callable | None = None` field
  - [ ] Add `artifact_type: str | None = None` field
  - [ ] Add docstrings explaining each field

- [ ] **Task 1.2: Create ToolInput and ToolOutput dataclasses**
  - [ ] Define `ToolInput` with `action_id`, `tool_name`, `payload`, `ctx`
  - [ ] Add `ToolInput.from_action(action: Action)` class method
  - [ ] Define `ToolOutput` with `success`, `data`, `error`, `undo_metadata`
  - [ ] Add `ToolOutput.to_dict()` method for serialization

- [ ] **Task 1.3: Create tool exceptions**
  - [ ] Create file `stageflow/tools/errors.py`
  - [ ] Define `ToolError` base exception
  - [ ] Define `ToolDeniedError` with `tool`, `behavior`, `allowed_behaviors`
  - [ ] Define `ToolApprovalDeniedError` with `tool`, `reason`
  - [ ] Define `ToolUndoError` with `tool`, `action_id`, `reason`

- [ ] **Task 1.4: Unit tests for ToolDefinition**
  - [ ] Create file `tests/unit/tools/test_definitions.py`
  - [ ] Test ToolDefinition creation with all fields
  - [ ] Test ToolInput.from_action() conversion
  - [ ] Test ToolOutput serialization

### Behavior Gating (Worker A)
- [ ] **Task 2.1: Implement behavior gating in ToolExecutor**
  - [ ] Update `stageflow/tools/executor.py`
  - [ ] Add `_check_behavior_gating(tool, ctx)` method
  - [ ] Get current behavior from `ctx.behavior`
  - [ ] If `tool.allowed_behaviors` is non-empty and behavior not in list, deny
  - [ ] Emit `tool.denied` event with reason "behavior_not_allowed"
  - [ ] Raise `ToolDeniedError` with helpful message

- [ ] **Task 2.2: Update tool registry with behavior metadata**
  - [ ] Update existing tool registrations to include `allowed_behaviors`
  - [ ] Example: `EDIT_DOCUMENT` allowed for `["doc_edit", "practice"]`
  - [ ] Example: `STORE_MEMORY` allowed for all behaviors (empty tuple)

- [ ] **Task 2.3: Unit tests for behavior gating**
  - [ ] Create file `tests/unit/tools/test_gating.py`
  - [ ] Test tool allowed when behavior in allowed_behaviors
  - [ ] Test tool allowed when allowed_behaviors is empty
  - [ ] Test tool denied when behavior not in allowed_behaviors
  - [ ] Test ToolDeniedError contains correct information

### Tool Event Lifecycle (Worker B)
- [ ] **Task 3.1: Create tool event types**
  - [ ] Create file `stageflow/tools/events.py`
  - [ ] Define `ToolInvokedEvent` with `tool_name`, `action_id`, `payload_summary`
  - [ ] Define `ToolStartedEvent` with `tool_name`, `action_id`
  - [ ] Define `ToolCompletedEvent` with `tool_name`, `action_id`, `duration_ms`, `output_summary`
  - [ ] Define `ToolFailedEvent` with `tool_name`, `action_id`, `error_code`, `error_message`
  - [ ] Define `ToolDeniedEvent` with `tool_name`, `action_id`, `reason`

- [ ] **Task 3.2: Implement event emission in execute()**
  - [ ] Add `_emit_tool_invoked(action, ctx)` at start of execute()
  - [ ] Add `_emit_tool_started(action, ctx)` before calling handler
  - [ ] Add `_emit_tool_completed(action, ctx, output)` on success
  - [ ] Add `_emit_tool_failed(action, ctx, error)` on exception
  - [ ] Include `pipeline_run_id` and `request_id` in all events

- [ ] **Task 3.3: Add timing instrumentation**
  - [ ] Record start time before handler call
  - [ ] Calculate `duration_ms` after handler returns
  - [ ] Include duration in `tool.completed` event
  - [ ] Add `tool_execution_duration_ms` metric

- [ ] **Task 3.4: Unit tests for tool events**
  - [ ] Create file `tests/unit/tools/test_events.py`
  - [ ] Test tool.invoked emitted at start
  - [ ] Test tool.started emitted before handler
  - [ ] Test tool.completed emitted on success with duration
  - [ ] Test tool.failed emitted on exception

### Undo Semantics (Worker B)
- [ ] **Task 4.1: Create undo metadata storage**
  - [ ] Create file `stageflow/tools/undo.py`
  - [ ] Define `UndoMetadata` dataclass with `action_id`, `tool_name`, `undo_data`, `created_at`
  - [ ] Create `UndoStore` class with `store()`, `get()`, `delete()` methods
  - [ ] Implement Redis-based storage (or DB fallback)
  - [ ] Add TTL for undo metadata (default: 1 hour)

- [ ] **Task 4.2: Store undo metadata on successful execution**
  - [ ] After successful tool execution, check if `tool.undoable`
  - [ ] If undoable, call `undo_store.store(action_id, output.undo_metadata)`
  - [ ] Log undo metadata storage

- [ ] **Task 4.3: Implement undo_action() method**
  - [ ] Add `async def undo_action(self, action_id: UUID, ctx: PipelineContext) -> bool`
  - [ ] Retrieve undo metadata from store
  - [ ] Get tool definition and verify it has undo_handler
  - [ ] Call `tool.undo_handler(undo_metadata)`
  - [ ] Emit `tool.undone` event on success
  - [ ] Emit `tool.undo_failed` event on failure
  - [ ] Delete undo metadata after successful undo

- [ ] **Task 4.4: Create undo events**
  - [ ] Define `ToolUndoneEvent` with `tool_name`, `action_id`, `duration_ms`
  - [ ] Define `ToolUndoFailedEvent` with `tool_name`, `action_id`, `error`

- [ ] **Task 4.5: Unit tests for undo flow**
  - [ ] Create file `tests/unit/tools/test_undo.py`
  - [ ] Test undo metadata stored for undoable tools
  - [ ] Test undo metadata not stored for non-undoable tools
  - [ ] Test undo_action() calls undo_handler
  - [ ] Test undo_action() emits tool.undone event
  - [ ] Test undo_action() handles missing metadata gracefully

### HITL Approval Flow (Worker C)
- [ ] **Task 5.1: Create approval_requests table**
  - [ ] Create Alembic migration
  - [ ] Table: `approval_requests` with columns:
    - `id` (UUID, primary key)
    - `pipeline_run_id` (UUID, foreign key)
    - `action_id` (UUID)
    - `tool_name` (TEXT)
    - `approval_message` (TEXT)
    - `status` (ENUM: pending, approved, denied, expired)
    - `decided_by` (UUID, nullable)
    - `decided_at` (TIMESTAMPTZ, nullable)
    - `created_at` (TIMESTAMPTZ)
  - [ ] Add index on `pipeline_run_id`
  - [ ] Add index on `status`

- [ ] **Task 5.2: Create ApprovalService**
  - [ ] Create file `stageflow/tools/approval.py`
  - [ ] Define `ApprovalService` class
  - [ ] Add `request_approval(action, ctx, tool) -> ApprovalRequest` method
  - [ ] Add `await_decision(request_id, timeout_seconds) -> ApprovalDecision` method
  - [ ] Add `record_decision(request_id, granted, user_id)` method

- [ ] **Task 5.3: Implement approval request flow**
  - [ ] In execute(), check if `tool.requires_approval`
  - [ ] Create approval request in database
  - [ ] Emit `approval.requested` event
  - [ ] Create `approval` UI artifact with request details
  - [ ] Wait for decision (with timeout)
  - [ ] If approved, continue execution
  - [ ] If denied, raise `ToolApprovalDeniedError`

- [ ] **Task 5.4: Create approval UI artifact**
  - [ ] Define `ApprovalArtifact` with `request_id`, `tool_name`, `message`, `options`
  - [ ] Options: `["approve", "deny"]`
  - [ ] Include action summary for user context

- [ ] **Task 5.5: Integrate with WebSocket**
  - [ ] Add WebSocket handler for approval decisions
  - [ ] Client sends: `{"type": "approval.decide", "request_id": "...", "decision": "approve|deny"}`
  - [ ] Server validates user has permission to decide
  - [ ] Server updates approval request and notifies waiting executor

- [ ] **Task 5.6: Create approval events**
  - [ ] Define `ApprovalRequestedEvent` with `request_id`, `tool_name`, `message`
  - [ ] Define `ApprovalDecidedEvent` with `request_id`, `decision`, `decided_by`

- [ ] **Task 5.7: Integration tests for HITL approval**
  - [ ] Create file `tests/integration/test_tool_approval.py`
  - [ ] Test approval request created for requires_approval tool
  - [ ] Test tool executes after approval granted
  - [ ] Test tool denied after approval denied
  - [ ] Test approval timeout handling

### Documentation
- [ ] **Task 6.1: Document tool system in ARCHITECTURE.md**
  - [ ] Add "Tool Execution" section
  - [ ] Document behavior gating
  - [ ] Document undo semantics
  - [ ] Document HITL approval flow
  - [ ] Include sequence diagrams

- [ ] **Task 6.2: Add tool development guide**
  - [ ] Create `docs/guides/creating-tools.md`
  - [ ] Document ToolDefinition fields
  - [ ] Document how to implement undo_handler
  - [ ] Include examples

---

## 🔍 Test Plan

### Unit Tests
| Component | Test File | Coverage |
|-----------|-----------|----------|
| ToolDefinition | `tests/unit/framework/test_tool_definition.py` | 100% |
| Behavior gating | `tests/unit/framework/test_tool_gating.py` | >90% |
| Undo semantics | `tests/unit/framework/test_tool_undo.py` | >90% |

### Integration Tests
| Flow | Test File |
|------|-----------|
| Tool allowed by behavior | `tests/integration/test_tool_executor.py` |
| Tool denied by behavior | `tests/integration/test_tool_executor.py` |
| HITL approval granted | `tests/integration/test_tool_approval.py` |
| HITL approval denied | `tests/integration/test_tool_approval.py` |

---

## 👁️ Observability Checklist

### Tool Events
- [ ] `tool.invoked` — action received, includes `tool_name`, `action_id`
- [ ] `tool.started` — execution beginning
- [ ] `tool.completed` — success, includes `duration_ms`, `output_summary`
- [ ] `tool.failed` — error, includes `error_code`, `error_message`
- [ ] `tool.undone` — action reversed
- [ ] `tool.undo_failed` — undo attempt failed

### Approval Events
- [ ] `approval.requested` — HITL approval needed
- [ ] `approval.decided` — user granted/denied

---

## ✔️ Completion Checklist

- [ ] Behavior gating enforced
- [ ] Full tool event lifecycle
- [ ] Undo semantics working
- [ ] HITL approval flow working
- [ ] Tests passing
- [ ] Docs updated

---

## 🔗 Related Documents

- [stageflow2.md](./stageflow2.md) §8.3 Actions & Tools
- [MASTER-ROADMAP.md](../MASTER-ROADMAP.md) — Gate G7
