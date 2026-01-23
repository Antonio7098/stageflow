# DAG Reliability, DX, and Performance Tracker

## Scope
Synthesizes DAG-001/003/005/006/008/010 findings covering cycle detection, guard failures, fan-out failure tolerance, deep DAG ergonomics, conditional branching, context complexity, and performance under burst load.

---

## Evidence Summary

| Report | Core Claim | Code Evidence | Verdict |
|--------|------------|---------------|---------|
| DAG-001 | Cycle detection & linting available | `CycleDetectedError` inherits from `PipelineValidationError`, captures cycle, structured remediation. `lint_pipeline()` validates graphs pre-run @stageflow/pipeline/spec.py @stageflow/cli/lint.py | **Confirmed functionality** |
| DAG-003 | Guard failures halt pipeline without retry routing | Stage execution raises `UnifiedStageExecutionError` on `StageStatus.FAIL`, no built-in retry. DAG scheduler executes dependencies once @stageflow/pipeline/dag.py | **Confirmed gap** |
| DAG-005 | No fan-out failure tolerance | Any failure propagates `UnifiedStageExecutionError`, cancels pending tasks. No `continue_on_failure` or partial success @stageflow/pipeline/dag.py | **Confirmed gap** |
| DAG-006 | Deep DAG ergonomics poor | Building thousand-stage chains requires manual `with_stage()`. No helpers for linear/parallel sequences @stageflow/pipeline/pipeline.py | **Confirmed gap** |
| DAG-008 | Conditional branching & cancellation semantics confusing | `StageOutput.cancel()` halts graph, router outputs don't short-circuit dependencies. Stages must read router data and `.skip()` @stageflow/core/stage_output.py @stageflow/pipeline/dag.py | **Confirmed gap** |
| DAG-010 | StageContext complexity high for tests/retries | Creating context requires wiring `PipelineContext`, `StageInputs`, timers. No concurrency limits, backpressure absent @stageflow/stages/context.py @stageflow/core/stage_context.py @stageflow/pipeline/dag.py | **Confirmed gap** |

---

## Consolidated Findings

### Critical Issues (P0)

**None** - All issues are reliability/DX gaps, not breaking bugs.

### High-Severity Issues (P1)

| ID | Issue | Impact | Evidence |
|----|-------|--------|----------|
| BUG-001 | No guard failure retry mechanism | Pipelines fail on recoverable guard issues | DAG-003: No retry routing after guard reject |
| BUG-005 | Fan-out failures cancel entire pipeline | Partial successes lost in multi-branch pipelines | DAG-005: No continue_on_failure mode |
| BUG-006 | Manual DAG building for deep chains | Ergonomic pain for complex workflows | DAG-006: No sequence generation helpers |
| BUG-008 | Router outputs don't prevent execution | Wasted work on unselected branches | DAG-008: Dependencies execute regardless |
| BUG-010 | No backpressure under burst load | Latency spikes degrade performance | DAG-010: Eager scheduling without limits |

### DX Issues

| ID | Issue | Severity |
|----|-------|----------|
| DX-001 | Cycle detection not documented | Medium |
| DX-003 | Guard retry patterns missing | Medium |
| DX-005 | Failure tolerance unclear | Medium |
| DX-006 | Deep DAG helpers absent | Medium |
| DX-008 | Conditional control flow confusing | Medium |
| DX-010 | Context creation verbose | Medium |

---

## Implementation Plan

### Phase 1: Documentation & DX Patches (Short Term)

| # | Status | Action | Owner | Effort | Impact |
|---|--------|--------|-------|--------|--------|
| 1 | Complete | **Cycle Detection Guide** – Add a “Detecting & Preventing Cycles” subsection to `docs/getting-started/quickstart.md` + `docs/advanced/composition.md`, referencing `CycleDetectedError`, `ContractErrorInfo`, and `lint_pipeline()` usage (sample failing builders, remediation checklist). | Docs | Low | High |
| 2 | Complete | **Guard Retry Cookbook** – Extend `docs/examples/agent-tools.md` with an autocorrection loop blueprint covering guard failure detection, manual retry routing, and loop counters. Provide `create_test_stage_context` snippet to reduce setup friction. | Runtime + Docs | Low | High |
| 3 | Complete | **Conditional Control Flow Notes** – Update `docs/advanced/composition.md` to clarify `StageOutput.cancel()` scope and the fact that router outputs don’t short-circuit dependencies today; include recommended patterns (e.g., downstream stages calling `.skip()` when route mismatches). | Docs | Low | Medium |

### Phase 2: Core Runtime Enhancements (Medium Term)

| # | Status | Enhancement | Priority | Design Considerations |
|---|--------|-------------|----------|----------------------|
| 1 | Complete | **Retry-on-Guard Failure** | P1 | Add optional `guard_retry_strategy` to `Pipeline`/`UnifiedStageGraph` that catches guard-stage `StageStatus.FAIL`, emits metrics, routes back to transformer until max iterations/timeout. Loop-detection guardrails (iteration limit + hash-based stagnation). |
| 2 | Not Started | **Continue-on-Failure Mode** | P1 | Introduce executor flag `continue_on_failure=True` that records failed outputs but keeps scheduling unrelated branches. Surfaces failures in final summary for fan-out diagnostics. |
| 3 | Not Started | **Conditional Dependencies MVP** | P1 | Extend `UnifiedStageSpec` with optional `when` expression (JMESPath over upstream outputs) to skip enqueuing stages whose predicates fail, avoiding wasted work. |
| 4 | Not Started | **Burst Load Backpressure** | P0/P1 | Add semaphore-backed concurrency limits (`max_active_stages`), optional queueing, `BurstHandlerInterceptor` watching P95 latency + active tasks to flip cancellation or shed load. |

### Phase 3: Ergonomics & Testing Utilities (Medium Term)

| # | Status | Enhancement | Priority | Design Considerations |
|---|--------|-------------|----------|----------------------|
| 1 | Not Started | **PipelineBuilder Helpers** | P1 | Provide `with_linear_chain(count, stage_factory)` and `with_parallel_stage(prefix, count, stage_factory)` utilities for deep/wide DAGs with minimal boilerplate. |
| 2 | Not Started | **Stage/Test Context Factories** | P1 | Ship `stageflow.testing.create_stage_context()` / `create_pipeline_context()` helpers wrapping verbose constructors for docs/tests. |
| 3 | Not Started | **Progress & Memory Hooks** | P2 | Add optional per-N-stage callbacks/logging to `UnifiedStageGraph` plus lightweight memory counters for long DAG runs. |

---

## Design Principles

### Speed
- Retry events add <2ms overhead (async emit)
- Concurrency limits prevent thrashing
- Conditional predicates add <1ms per stage (JMESPath eval)

### Safety
- **Fail-explicit over fail-silent**: Emit events for guard retries, cancellations
- **No behavior changes in core**: All enhancements are opt-in or additive
- **Opt-in complexity**: Advanced routing in Plus package

### Observability
- Retry events follow `{stage}.{action}` naming: `guard.retry_attempt`, `guard.retry_success`
- Failure collection surfaces partial results
- Backpressure metrics track queue depth and latency

### Reliability
- Guard retries prevent false negatives
- Failure tolerance enables resilient fan-out
- Conditional edges prevent wasted computation

### SOLID Principles
- **Single Responsibility**: Each enhancement handles one DAG concern (retry, failure, branching)
- **Open/Closed**: Core DAG unchanged; extensions via UnifiedStageGraph
- **Liskov Substitution**: Retry stages implement same Stage protocol
- **Interface Segregation**: Minimal interfaces for predicates and limits
- **Dependency Inversion**: Scheduler depends on abstractions, not concretions

### Scalability
- Conditional dependencies reduce execution graph size
- Concurrency limits scale to available resources
- Failure tolerance enables larger fan-out without fragility

---

## Test Coverage Requirements

| Component | Test Type | Coverage Target |
|-----------|-----------|-----------------|
| Guard retry | Unit + Integration | Retry loops, stagnation detection |
| Failure tolerance | E2E | Partial success collection |
| Conditional deps | Unit | Predicate evaluation, scheduling |
| Backpressure | Integration | Concurrency limits, queueing |
| Ergonomics | Unit | Helper generation accuracy |

---

## Next Actions

1. **Immediate**: Kick off docs PR covering cycle detection, guard retries, and cancel semantics (target: this sprint)
2. **This Sprint**: Draft RFC for executor-level `guard_retry_strategy` + `continue_on_failure` so we can land guard/fan-out fixes together
3. **Next Sprint**: Schedule follow-up spike to prototype conditional dependency predicates and semaphore-based concurrency caps

---

## DX Score Summary

| Report | Score | Key Friction |
|--------|-------|--------------|
| DAG-001 | 4.5/5 | Cycle detection now documented |
| DAG-003 | 3.0/5 | Retry implemented but not all patterns |
| DAG-005 | 1.5/5 | No failure tolerance yet |
| DAG-006 | 1.0/5 | No ergonomics helpers |
| DAG-008 | 2.0/5 | Conditional deps not implemented |
| DAG-010 | 1.5/5 | Backpressure missing |
| **Average** | **2.3/5** | Partial implementation |

---

*Synthesized from DAG-001, DAG-003, DAG-005, DAG-006, DAG-008, DAG-010 final reports.*
