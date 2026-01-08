# STF-SPR-004: Subpipeline Runs

**Status:** 🔴 Not Started  
**Branch:** `feature/stf-spr-004-subpipeline-runs`  
**Duration:** 1 week  
**Dependencies:** STF-SPR-003 (Advanced ToolExecutor)

---

## 📅 Sprint Details & Goals

### Overview
Enable agent actions to spawn child pipeline runs for complex operations (e.g., document editing, search, delegation). Subpipeline runs maintain correlation with parent runs for end-to-end observability.

### Primary Goal (Must-Have)
- **ToolExecutor can spawn child PipelineRuns for complex actions**
- **Child runs store `parent_run_id` and `parent_stage_id`**
- **Parent cancellation cascades to children**
- **Child failures bubble up as `tool.*` events**

### Success Criteria
- [ ] `spawn_subpipeline()` method on ToolExecutor
- [ ] Child runs have `parent_run_id`, `parent_stage_id`, `correlation_id`
- [ ] Parent cancellation cancels all child runs
- [ ] Child pipeline events include both parent and child run IDs
- [ ] Central Pulse can render run trees
- [ ] Integration tests pass

---

## 🏗️ Architecture & Design

### Subpipeline Creation

```python
class ToolExecutor:
    async def spawn_subpipeline(
        self,
        pipeline_name: str,
        ctx: PipelineContext,
        action: Action,
    ) -> SubpipelineResult:
        """Spawn a child pipeline for complex tool execution."""
        
        # Create child run with correlation
        child_run_id = uuid.uuid4()
        child_ctx = ctx.fork(
            pipeline_run_id=child_run_id,
            parent_run_id=ctx.pipeline_run_id,
            parent_stage_id=ctx.current_stage_id,
            correlation_id=action.id,
        )
        
        # Register child for cancellation propagation
        self._register_child(ctx.pipeline_run_id, child_run_id)
        
        # Get and execute child pipeline
        pipeline = self.registry.get_pipeline(pipeline_name)
        try:
            result = await self.orchestrator.run(
                pipeline_run_id=child_run_id,
                pipeline=pipeline,
                ctx=child_ctx,
            )
            return SubpipelineResult(success=True, data=result)
        except Exception as e:
            # Emit tool.failed with child run reference
            await self._emit_child_failure(ctx, action, child_run_id, e)
            raise
        finally:
            self._unregister_child(ctx.pipeline_run_id, child_run_id)
```

### PipelineContext.fork()

```python
class PipelineContext:
    def fork(
        self,
        pipeline_run_id: UUID,
        parent_run_id: UUID,
        parent_stage_id: str,
        correlation_id: UUID,
    ) -> 'PipelineContext':
        """Create a child context with read-only view of parent data."""
        return PipelineContext(
            pipeline_run_id=pipeline_run_id,
            parent_run_id=parent_run_id,
            parent_stage_id=parent_stage_id,
            correlation_id=correlation_id,
            # Read-only snapshot of parent data
            data=FrozenDict(self.data),
            # Child gets own ContextBag for outputs
            context_bag=ContextBag(),
            # Inherit auth context
            auth_context=self.auth_context,
        )
```

### Cancellation Propagation

```python
class PipelineOrchestrator:
    _child_runs: dict[UUID, set[UUID]] = {}  # parent_id -> child_ids
    
    async def cancel_with_children(self, pipeline_run_id: UUID) -> None:
        """Cancel a run and all its children."""
        children = self._child_runs.get(pipeline_run_id, set())
        
        # Cancel children first (depth-first)
        for child_id in children:
            await self.cancel_with_children(child_id)
        
        # Then cancel self
        await self._mark_canceled(pipeline_run_id)
```

### Event Correlation

All child events include both IDs for end-to-end tracing:

```json
{
  "type": "stage.llm.completed",
  "pipeline_run_id": "child-uuid",
  "parent_run_id": "parent-uuid",
  "parent_stage_id": "tool_executor",
  "correlation_id": "action-uuid",
  "data": { ... }
}
```

---

## 🧩 Parallelization Plan (A/B)

### Worker A (Subpipeline Spawning)
**Owns:** Child pipeline creation and execution

- **Task 1.1:** Implement `PipelineContext.fork()`
- **Task 1.2:** Implement `ToolExecutor.spawn_subpipeline()`
- **Task 1.3:** Add parent/child correlation fields to `PipelineRun` model
- **Task 1.4:** Unit tests for context forking

### Worker B (Cancellation + Events)
**Owns:** Cascading cancellation and event correlation

- **Task 2.1:** Implement child run tracking in orchestrator
- **Task 2.2:** Implement `cancel_with_children()`
- **Task 2.3:** Add parent_run_id to all child events
- **Task 2.4:** Integration tests for cancellation propagation

---

## ✅ Detailed Task List

### Setup & Infrastructure
- [ ] **Task 0.1: Review existing PipelineRun model**
  - [ ] Document current run lifecycle

- [ ] **Task 0.2: Review PipelineContext**
  - [ ] Read `stageflow/stages/context.py`
  - [ ] Understand current data passing patterns
  - [ ] Identify what needs to be shared vs isolated in child contexts

### Database Schema Updates (Worker A)
- [ ] **Task 1.1: Update PipelineRun model**
  - [ ] Add `parent_run_id: UUID | None` column (nullable, foreign key to self)
  - [ ] Add `parent_stage_id: str | None` column (stage that spawned this run)
  - [ ] Add `correlation_id: UUID | None` column (action ID that triggered spawn)

- [ ] **Task 1.2: Create Alembic migration**
  - [ ] Create migration file for new columns
  - [ ] Add foreign key constraint: `parent_run_id REFERENCES pipeline_runs(id)`
  - [ ] Add index on `parent_run_id` for efficient child lookups
  - [ ] Add index on `correlation_id` for action tracing
  - [ ] Test migration up and down

- [ ] **Task 1.3: Update PipelineRun queries**
  - [ ] Add `get_children(run_id) -> list[PipelineRun]` method
  - [ ] Add `get_root_run(run_id) -> PipelineRun` method (traverse to top)
  - [ ] Add `get_run_tree(run_id) -> dict` method (full hierarchy)

- [ ] **Task 1.4: Unit tests for PipelineRun updates**
  - [ ] Create file `tests/unit/models/test_pipeline_run_hierarchy.py`
  - [ ] Test parent-child relationship creation
  - [ ] Test get_children() returns correct runs
  - [ ] Test get_root_run() traverses to top
  - [ ] Test cascade delete behavior (if applicable)

### PipelineContext.fork() (Worker A)
- [ ] **Task 2.1: Create FrozenDict helper**
  - [ ] Create file `stageflow/utils/frozen.py`
  - [ ] Define `FrozenDict` class that wraps dict as read-only
  - [ ] Raise `TypeError` on any mutation attempt
  - [ ] Add `to_dict()` method for when mutation is needed

- [ ] **Task 2.2: Implement PipelineContext.fork() method**
  - [ ] Update `stageflow/stages/context.py`
  - [ ] Add `fork(pipeline_run_id, parent_run_id, parent_stage_id, correlation_id) -> PipelineContext`
  - [ ] Create new PipelineContext with new run ID
  - [ ] Wrap parent data in FrozenDict (read-only snapshot)
  - [ ] Create fresh ContextBag for child outputs
  - [ ] Copy auth_context (inherited, not forked)
  - [ ] Copy org_id (inherited)

- [ ] **Task 2.3: Add fork metadata to context**
  - [ ] Add `is_child_run: bool` property
  - [ ] Add `parent_run_id: UUID | None` property
  - [ ] Add `correlation_id: UUID | None` property
  - [ ] Add `get_parent_data(key)` method for explicit parent access

- [ ] **Task 2.4: Unit tests for context forking**
  - [ ] Create file `tests/unit/stages/test_context_fork.py`
  - [ ] Test fork() creates new context with correct IDs
  - [ ] Test forked context has read-only parent data
  - [ ] Test forked context has fresh ContextBag
  - [ ] Test auth_context is inherited
  - [ ] Test mutation of parent data raises TypeError

### Subpipeline Spawning (Worker A)
- [ ] **Task 3.1: Add spawn_subpipeline() to ToolExecutor**
  - [ ] Update `stageflow/tools/executor.py`
  - [ ] Add `async def spawn_subpipeline(pipeline_name, ctx, action) -> SubpipelineResult`
  - [ ] Generate new child run ID
  - [ ] Call `ctx.fork()` to create child context
  - [ ] Register child with orchestrator for tracking

- [ ] **Task 3.2: Implement subpipeline execution**
  - [ ] Get pipeline from registry by name
  - [ ] Call `orchestrator.run(child_run_id, pipeline, child_ctx)`
  - [ ] Wrap result in `SubpipelineResult` dataclass
  - [ ] Handle exceptions and emit appropriate events

- [ ] **Task 3.3: Create SubpipelineResult dataclass**
  - [ ] Define `SubpipelineResult` with `success`, `data`, `error`, `child_run_id`
  - [ ] Add `to_tool_output()` method for integration with tool flow

- [ ] **Task 3.4: Unit tests for spawn_subpipeline**
  - [ ] Create file `tests/unit/tools/test_spawn_subpipeline.py`
  - [ ] Test spawn creates child run with correct parent IDs
  - [ ] Test spawn executes child pipeline
  - [ ] Test spawn returns SubpipelineResult
  - [ ] Test spawn handles pipeline not found error

### Child Run Tracking (Worker B)
- [ ] **Task 4.1: Add child tracking to PipelineOrchestrator**
  - [ ] Update `stageflow/stages/orchestrator.py`
  - [ ] Add `_child_runs: dict[UUID, set[UUID]]` class attribute
  - [ ] Add `_register_child(parent_id, child_id)` method
  - [ ] Add `_unregister_child(parent_id, child_id)` method
  - [ ] Add `_get_children(parent_id) -> set[UUID]` method

- [ ] **Task 4.2: Register children during spawn**
  - [ ] Call `_register_child()` before executing child pipeline
  - [ ] Call `_unregister_child()` in finally block after execution
  - [ ] Handle case where parent completes before child

- [ ] **Task 4.3: Unit tests for child tracking**
  - [ ] Create file `tests/unit/stages/test_child_tracking.py`
  - [ ] Test register adds child to parent's set
  - [ ] Test unregister removes child from set
  - [ ] Test get_children returns correct set
  - [ ] Test concurrent registration is thread-safe

### Cancellation Propagation (Worker B)
- [ ] **Task 5.1: Implement cancel_with_children() method**
  - [ ] Add `async def cancel_with_children(run_id) -> None` to orchestrator
  - [ ] Get all children of the run
  - [ ] Recursively cancel children first (depth-first)
  - [ ] Then cancel the parent run
  - [ ] Emit `pipeline.canceled` event for each

- [ ] **Task 5.2: Update existing cancel() to use cascade**
  - [ ] Modify `cancel(run_id)` to call `cancel_with_children()`
  - [ ] Add `cascade: bool = True` parameter for opt-out
  - [ ] Log cancellation cascade path

- [ ] **Task 5.3: Handle in-flight child runs**
  - [ ] Check if child is currently executing
  - [ ] Set cancellation flag that stages can check
  - [ ] Stages should check `ctx.is_canceled` and exit early

- [ ] **Task 5.4: Integration tests for cancellation**
  - [ ] Create file `tests/integration/test_cancellation_cascade.py`
  - [ ] Test parent cancellation cancels single child
  - [ ] Test parent cancellation cascades to grandchildren
  - [ ] Test child cancellation does not affect parent
  - [ ] Test cancellation during child execution

### Event Correlation (Worker B)
- [ ] **Task 6.1: Update event emission for child runs**
  - [ ] Modify all event emission to include `parent_run_id` if present
  - [ ] Include `correlation_id` in events
  - [ ] Include `is_child_run: true` flag in child events

- [ ] **Task 6.2: Create subpipeline-specific events**
  - [ ] Define `PipelineSpawnedChildEvent` with `parent_run_id`, `child_run_id`, `pipeline_name`
  - [ ] Define `PipelineChildCompletedEvent` with `parent_run_id`, `child_run_id`, `success`
  - [ ] Define `PipelineChildFailedEvent` with `parent_run_id`, `child_run_id`, `error`

- [ ] **Task 6.3: Emit events during subpipeline lifecycle**
  - [ ] Emit `pipeline.spawned_child` when child created
  - [ ] Emit `pipeline.child_completed` when child succeeds
  - [ ] Emit `pipeline.child_failed` when child errors
  - [ ] Include duration_ms in completion events

- [ ] **Task 6.4: Unit tests for event correlation**
  - [ ] Create file `tests/unit/stages/test_event_correlation.py`

### Central Pulse Integration
- [ ] **Task 7.1: Update Central Pulse queries**
  - [ ] Add query to fetch run tree by root ID
  - [ ] Add query to fetch all events for a run tree
  - [ ] Optimize queries for large trees

- [ ] **Task 7.2: Document run tree visualization**
  - [ ] Document expected UI for run trees
  - [ ] Document how to navigate parent ↔ child
  - [ ] Document event timeline across tree

### Documentation
- [ ] **Task 8.1: Document subpipeline patterns in ARCHITECTURE.md**
  - [ ] Add "Subpipeline Runs" section
  - [ ] Document when to use subpipelines
  - [ ] Document context forking semantics
  - [ ] Document cancellation behavior
  - [ ] Include sequence diagram

- [ ] **Task 8.2: Add subpipeline development guide**
  - [ ] Create `docs/guides/subpipelines.md`
  - [ ] Document how to spawn subpipelines from tools
  - [ ] Document data passing patterns
  - [ ] Include examples

---

## 🔍 Test Plan

### Unit Tests
| Component | Test File | Coverage |
|-----------|-----------|----------|
| PipelineContext.fork | `tests/unit/framework/test_context_fork.py` | 100% |
| Child tracking | `tests/unit/framework/test_child_runs.py` | >90% |

### Integration Tests
| Flow | Test File |
|------|-----------|
| Spawn child pipeline | `tests/integration/test_subpipelines.py` |
| Cascading cancellation | `tests/integration/test_subpipelines.py` |
| Child failure handling | `tests/integration/test_subpipelines.py` |

---

## 👁️ Observability Checklist

### Event Correlation
- [ ] All child events include `parent_run_id`
- [ ] All child events include `correlation_id` (action that spawned)
- [ ] `pipeline.spawned_child` event when child created
- [ ] `pipeline.child_completed` event when child finishes
- [ ] `pipeline.child_failed` event when child errors

### Central Pulse Integration
- [ ] Run tree visualization shows parent-child relationships
- [ ] Clicking child run shows parent context
- [ ] Cancellation events show cascade path

---

## ✔️ Completion Checklist

- [ ] Subpipeline spawning works
- [ ] Parent-child correlation in events
- [ ] Cancellation cascades correctly
- [ ] Child failures bubble up
- [ ] Tests passing
- [ ] Docs updated

---

## 🔗 Related Documents

- [stageflow2.md](./stageflow2.md) §8.7 Subpipeline Runs
- [MASTER-ROADMAP.md](../MASTER-ROADMAP.md)
