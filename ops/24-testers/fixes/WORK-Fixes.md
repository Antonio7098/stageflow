# WORK Stage Side Effects & Reliability Tracker

## Scope
Synthesizes WORK-001, WORK-002, WORK-003, WORK-005, WORK-010 findings covering tool execution sandboxing, idempotency guarantees, saga pattern, retry logic with exponential backoff, and rollback/undo capability.

---

## Evidence Summary

| Report | Core Claim | Code Evidence | Verdict |
|--------|------------|---------------|---------|
| WORK-001 | No native sandboxing for tool execution | `StageKind.WORK` exists (`@stageflow/core/stage_enums.py:17`) but no sandbox primitives. Tool execution relies on external isolation. | **Confirmed gap** |
| WORK-001 | Tool registry API changed without docs update | `ToolRegistry.register_tool()` renamed to `register()`. | **Confirmed DX issue** |
| WORK-002 | WORK stages NOT idempotent by default | No idempotency key validation in stage execution. Each retry creates duplicate side effects. | **Confirmed gap** |
| WORK-002 | Concurrent duplicates bypass idempotency checks | Race conditions at 50+ concurrent requests. | **Confirmed bug** |
| WORK-003 | Saga pattern works with custom implementation | `SagaStateMachine` correctly tracks compensation order. | **Confirmed strength** |
| WORK-003 | `datetime.utcnow()` deprecated | Will break in future Python versions. | **Confirmed bug** |
| WORK-005 | No built-in RetryInterceptor | `StageOutput.retry()` exists but no automatic handling. | **Confirmed gap** |
| WORK-005 | All backoff strategies implemented correctly | No Jitter, Full Jitter, Equal Jitter, Decorrelated all work. | **Confirmed strength** |
| WORK-010 | ContextSnapshot enables safe checkpointing | Immutable design, `to_dict()`/`from_dict()` serialization. | **Confirmed strength** |
| WORK-010 | No automatic retry on StageOutput.fail | Pipeline stops immediately, requires interceptor. | **Confirmed behavior** |

---

## Consolidated Findings

### Critical Issues (P0)

| ID | Issue | Impact | Evidence |
|----|-------|--------|----------|
| BUG-073 | Concurrent duplicate requests bypass idempotency checks | Data corruption, double billing | WORK-002: 50+ concurrent = 2 inserts |

### High-Severity Issues (P1)

| ID | Issue | Impact | Evidence |
|----|-------|--------|----------|
| BUG-072 | Idempotency not enforced in WORK stages by default | Duplicate database records, notification spam | WORK-002: Each retry = new insert |
| BUG-075 | Replay attacks not prevented | Attackers can cause duplicate operations | WORK-002: Captured requests re-execute |
| BUG-082 | No automatic retry on StageOutput.fail | Requires manual interceptor configuration | WORK-010: Pipeline stops immediately |

### Medium-Severity Issues

| ID | Issue | Impact |
|----|-------|--------|
| BUG-074 | Parameter mismatch not detected | Silent skip instead of error |
| BUG-076 | `datetime.utcnow()` deprecated | Future Python compatibility |

### DX Issues

| ID | Issue | Severity |
|----|-------|----------|
| DX-068 | Tool registry API documentation gaps | Medium |
| DX-070 | Missing Saga pattern documentation | Medium |
| DX-071 | Missing retry documentation | Medium |
| DX-075 | Checkpoint/restore patterns not documented | Medium |

### Strengths

| ID | Strength | Evidence |
|----|----------|----------|
| STR-088 | Stage contract framework enables idempotency patterns | StageOutput.ok/skip/fail methods |
| STR-089 | Saga state machine design correct | Reverse-order compensation tracking |
| STR-095 | ContextSnapshot immutability enables safe checkpointing | to_dict/from_dict serialization |

---

## Implementation Plan

### Phase 1: Critical Fixes (Immediate)

| # | Action | Priority | Effort | Impact |
|---|--------|----------|--------|--------|
| 1 | **Implement atomic idempotency checks** - ✅ `IdempotencyInterceptor` now serializes in-flight work with per-key asyncio locks so duplicates either reuse the cached result or fail fast on param mismatch. | P0 | High | Critical |
| 2 | **Replace `datetime.utcnow()`** - ✅ All Stageflow docs now use `datetime.now(timezone.utc)` to avoid deprecated APIs. | P1 | Low | Medium |
| 3 | **Document idempotency patterns** - ✅ Added `docs/advanced/idempotency.md`, linked it from docs index, and updated examples to cover key design + store selection. | P0 | Medium | High |

#### Fix Log (2026-01-23)

1. **IdempotencyInterceptor shipped** (`stageflow/pipeline/idempotency.py`) – introduced a reusable interceptor + async store abstraction that caches `StageResult`s per idempotency key, detects parameter mismatches, and short-circuits duplicate executions to close BUG-073/BUG-072.
2. **Default pipeline hardening** (`stageflow/pipeline/interceptors.py`) – wired the new interceptor into `get_default_interceptors()` (opt-out via `include_idempotency=False`) and marked idempotency failures as `CriticalInterceptorError`s so duplicates fail fast instead of corrupting state.
3. **Config surface** – pipelines can supply shared `IdempotencyStore`s and populate `ctx.data["idempotency_key"]` / `ctx.data["idempotency_params"]` to take advantage of the protection without code changes in individual WORK stages.
4. **Atomic duplicate control** (`stageflow/pipeline/idempotency.py`, `tests/unit/pipeline/test_idempotency_interceptor.py`) – added per-key asyncio locks so concurrent duplicates wait for the first successful run and receive the cached `StageResult`. Added regression test covering the in-flight blocking behavior.
5. **Idempotency playbook** (`docs/advanced/idempotency.md`, `docs/index.md`) – published the Phase 1 documentation deliverable with key design, store selection, and observability guidance; index now links to it for discoverability.
6. **UTC-safe samples** (`docs/guides/context.md`, `docs/guides/observability.md`, `docs/advanced/custom-interceptors.md`, `docs/api/events.md`, `docs/api/wide-events.md`, `docs/examples/chat.md`) – replaced all `datetime.utcnow()` occurrences with `datetime.now(timezone.utc)` to close BUG-076 and keep tutorials future-proof.

### Phase 2: Documentation & DX (Short Term)

| # | Status | Action | Owner | Effort |
|---|--------|--------|-------|--------|
| 1 | ✅ **Saga Pattern Guide** - Added `docs/advanced/saga-pattern.md` with compensation handlers, state machines, and rollback strategies | Docs | Medium |
| 2 | ✅ **Retry Patterns Guide** - Added `docs/advanced/retry-backoff.md` covering exponential/linear/constant backoff, jitter strategies, and RetryInterceptor usage | Docs | Medium |
| 3 | ✅ **Checkpoint Guide** - Added `docs/advanced/checkpointing.md` for long-running pipeline state persistence and recovery | Docs | Medium |
| 4 | ✅ **Tool Registry docs** - Updated `docs/api/tools.md` with current API, examples, and sandboxing considerations | Docs | Low |
| 5 | ✅ **Sandboxing Guide** - Added `docs/advanced/tool-sandboxing.md` covering Docker/process isolation, network policies, and resource quotas | Docs | Medium |

### Phase 3: Core Runtime Enhancements (Medium Term)

| # | Status | Enhancement | Priority | Design |
|---|--------|-------------|----------|--------|
| 1 | ✅ **IdempotencyInterceptor** | P0 | Extract idempotency_key from context, check store before execution, return cached result for duplicates, validate parameters match. |
| 2 | ✅ **RetryInterceptor** | P1 | Configurable max_attempts, base_delay, backoff_strategy, jitter. Automatic retry on `StageOutput.retry()` or transient errors. |
| 3 | ✅ **Cached Result Return** | P1 | For duplicate requests, return cached `StageOutput` instead of re-executing. |
| 4 | ✅ **Parameter Validation** | P2 | Detect parameter mismatches for same idempotency key. Fail with clear error. |

### Phase 4: Stageflow Plus Components (Medium Term)

| ID | Status | Component | Type | Priority | Use Case |
|----|--------|-----------|------|----------|----------|
| IMP-095 | Not Started | `SandboxStage` | Stagekind | P0 | Isolated tool execution with configurable security policies |
| IMP-096 | Not Started | `NetworkPolicyTool` | Security | P0 | Network egress controls for tools |
| IMP-097 | Not Started | `ResourceQuotaInterceptor` | Reliability | P0 | CPU, memory, file system limits |
| IMP-098 | Not Started | `IdempotencyInterceptor` | Interceptor | P0 | Automatic duplicate detection |
| IMP-099 | Not Started | `IdempotentStageMixin` | Mixin | P1 | Zero-code idempotency integration |
| IMP-100 | Not Started | `SagaOrchestrator` | Stagekind | P1 | Pre-built saga execution with compensation |
| IMP-101 | Not Started | `RetryStage` | Stagekind | P1 | Wrap stages with exponential backoff |
| IMP-104 | Not Started | `RetryInterceptor` | Interceptor | P1 | Automatic retry handling |
| IMP-105 | Not Started | `RetryStage` | Stagekind | P1 | Drop-in retry capability |
| IMP-111 | Not Started | `CheckpointStage` | Stagekind | P1 | State capture for rollback |
| IMP-112 | Not Started | `CompensatingActionStage` | Stagekind | P1 | Saga compensation support |

---

## Design Principles

### Speed
- Idempotency check: <5ms with in-memory cache, <50ms with database
- Retry backoff: Configurable delays, no framework overhead
- Checkpoint serialization: 0.3ms (confirmed)

### Safety
- **Fail-closed for duplicates**: Return cached result, don't re-execute
- **Atomic idempotency checks**: Database-level locking prevents race conditions
- **Parameter validation**: Detect intent mismatches, fail explicitly
- **Sandbox isolation**: External containers/microVMs for untrusted tools

### Observability
- `work.idempotency_hit` event when duplicate detected
- `work.retry_attempt` event with attempt number, delay, error
- `work.compensation_executed` event for saga rollbacks
- Audit trail: All tool executions logged with parameters

### Reliability
- Idempotency keys scoped to (client_id, operation)
- Saga compensation in reverse order
- Circuit breaker for external service calls
- Checkpoint/restore for crash recovery

### SOLID Principles
- **Single Responsibility**: Each interceptor handles one concern (idempotency, retry, sandbox)
- **Open/Closed**: Interceptors compose without modifying stages
- **Liskov Substitution**: All WORK stages implement `Stage` protocol
- **Interface Segregation**: Minimal interceptor interface (before, after, on_error)
- **Dependency Inversion**: Stages depend on abstractions (idempotency store), not concretions

### Scalability
- Idempotency store can be Redis, DynamoDB, or in-memory
- Retry with jitter prevents thundering herd
- Saga state machine is per-run, not global

---

## Code Evidence: Existing Infrastructure

```python
@stageflow/core/stage_enums.py:17
WORK = "work"  # Assessment, Triage, Persist - side effects

@stageflow/pipeline/interceptors.py:120-157
class BaseInterceptor(ABC):
    """Base class for stage interceptors."""
    name: str = "base_interceptor"
    priority: int = 100
    
    @abstractmethod
    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        ...
    
    @abstractmethod
    async def after(self, _stage_name: str, _result: StageResult, _ctx: PipelineContext) -> None:
        ...
    
    async def on_error(self, _stage_name: str, _error: Exception, _ctx: PipelineContext) -> ErrorAction:
        ...

@stageflow/core/stage_enums.py:28
RETRY = "retry"  # Stage failed but is retryable
```

---

## Proposed API: IdempotencyInterceptor

```python
# stageflow.plus.idempotency (proposed)

class IdempotencyInterceptor(BaseInterceptor):
    """Interceptor that enforces idempotency on WORK stages."""
    
    name = "idempotency"
    priority = 10  # Run early (outer wrapper)
    
    def __init__(
        self,
        store: IdempotencyStore,
        key_extractor: Callable[[PipelineContext], str] | None = None,
        ttl_seconds: int = 86400,  # 24 hours
        validate_params: bool = True,
    ):
        ...
    
    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        key = self._extract_key(ctx)
        cached = await self._store.get(key)
        if cached:
            if self._validate_params and cached.params != self._extract_params(ctx):
                raise IdempotencyParamMismatch(key, cached.params, self._extract_params(ctx))
            return InterceptorResult(stage_ran=False, result=cached.result)
        return None
    
    async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        key = self._extract_key(ctx)
        await self._store.set(key, result, self._extract_params(ctx), ttl=self._ttl)
```

---

## Proposed API: RetryInterceptor

```python
# stageflow.plus.retry (proposed)

class RetryInterceptor(BaseInterceptor):
    """Interceptor that automatically retries failed stages."""
    
    name = "retry"
    priority = 20  # Run after idempotency
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay_ms: int = 1000,
        max_delay_ms: int = 30000,
        backoff_strategy: str = "exponential",  # exponential, linear, constant
        jitter_strategy: str = "full",  # none, full, equal, decorrelated
        retry_on: tuple[type[Exception], ...] = (TransientError,),
    ):
        ...
    
    async def on_error(self, stage_name: str, error: Exception, ctx: PipelineContext) -> ErrorAction:
        if not isinstance(error, self._retry_on):
            return ErrorAction.FAIL
        
        attempt = ctx.data.get("_retry_attempt", 0) + 1
        if attempt >= self._max_attempts:
            return ErrorAction.FAIL
        
        delay = self._calculate_delay(attempt)
        await asyncio.sleep(delay / 1000)
        ctx.data["_retry_attempt"] = attempt
        return ErrorAction.RETRY
```

---

## Test Coverage Requirements

| Component | Test Type | Coverage Target |
|-----------|-----------|-----------------|
| Idempotency check | Unit | Duplicate returns cached result |
| Concurrent duplicates | Integration | Only one execution at 50+ concurrent |
| Parameter validation | Unit | Mismatch raises error |
| Retry backoff | Unit | All strategies compute correctly |
| Saga compensation | Integration | Reverse-order execution |
| Checkpoint/restore | Unit | State serialization roundtrip |

---

## Next Actions

1. **Immediate**: Document idempotency patterns (2 days)
2. **Immediate**: Replace `datetime.utcnow()` calls (1 day)
3. **This Sprint**: Implement `IdempotencyInterceptor` prototype (3 days)
4. **This Sprint**: Create `docs/advanced/saga-pattern.md` (1 day)
5. **Next Sprint**: Implement `RetryInterceptor` with all backoff strategies
6. **Backlog**: Design `SandboxStage` API with container integration

---

## DX Score Summary

| Report | Score | Key Friction |
|--------|-------|--------------|
| WORK-001 | 2.7/5 | API documentation gaps |
| WORK-002 | 2.9/5 | No built-in idempotency |
| WORK-003 | 3.5/5 | Missing Saga documentation |
| WORK-005 | 3.5/5 | Missing retry documentation |
| WORK-010 | 3.2/5 | Checkpoint patterns undocumented |
| **Average** | **3.16/5** | Side effect patterns underdocumented |

---

## Security Considerations

### Tool Execution Sandboxing

| Approach | Isolation Level | Performance | Recommendation |
|----------|-----------------|-------------|----------------|
| Process isolation | Low | High | Development only |
| Container (Docker) | Medium | Medium | Standard production |
| MicroVM (Firecracker) | High | Medium | High-security workloads |
| WASM | Medium | High | Emerging option |

### Idempotency Security

- **Token hijacking**: Scope keys to (client_id, operation)
- **Replay attacks**: Add timestamp validation, TTL expiration
- **SQL injection in keys**: Parameterized queries, input validation

---

*Synthesized from WORK-001, WORK-002, WORK-003, WORK-005, WORK-010 final reports.*
