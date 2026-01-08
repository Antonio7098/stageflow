# STF-SPR-005: Testing Harness + Benchmarking

**Status:** 🔴 Not Started  
**Branch:** `feature/stf-spr-005-testing-benchmarking`  
**Duration:** 1 week  
**Dependencies:** STF-SPR-004 (Subpipeline Runs)

---

## 📅 Sprint Details & Goals

### Overview
Build comprehensive testing infrastructure for the stageflow framework. Create benchmark suite for continuous performance monitoring.

### Primary Goal (Must-Have)
- **Property-based tests for DAG validity, composition, and conflict detection**
- **Contract tests for stage event emission**
- **Fault-injection tests for provider outages**
- **Benchmark suite with latency budgets per kernel**

### Success Criteria
- [ ] Property-based tests cover all invariants
- [ ] Contract tests verify stage protocol compliance
- [ ] Fault-injection tests simulate provider failures
- [ ] Benchmark gates enforce latency budgets
- [ ] Central Pulse dashboard for performance trends

---

## 🏗️ Architecture & Design

### Test Pyramid

```
                    ┌─────────────┐
                    │   E2E Tests │  (10-20)
                   ─┴─────────────┴─
                  ┌─────────────────┐
                  │ Integration Tests│ (50-100)
                 ─┴─────────────────┴─
                ┌─────────────────────┐
                │    Contract Tests    │ (30-50)
               ─┴─────────────────────┴─
              ┌─────────────────────────┐
              │    Property Tests        │ (20-30)
             ─┴─────────────────────────┴─
            ┌───────────────────────────────┐
            │        Unit Tests              │ (100-200)
           ─┴───────────────────────────────┴─
```

### Property-Based Tests (Hypothesis)

```python
# DAG validity
@given(stage_specs())
def test_dag_no_cycles(specs):
    """Generated DAGs never contain cycles."""
    pipeline = Pipeline("test", specs)
    graph = pipeline.build()
    assert not graph.has_cycles()

# Composition associativity
@given(pipelines(), pipelines(), pipelines())
def test_compose_associativity(a, b, c):
    """Pipeline composition is associative."""
    left = a.compose(b).compose(c)
    right = a.compose(b.compose(c))
    assert left.stages == right.stages

# ContextBag conflict detection
@given(st.text(), st.binary())
def test_context_bag_conflict(key, value):
    """Writing same key twice always raises."""
    bag = ContextBag()
    asyncio.run(bag.write(key, value, "stage_a"))
    with pytest.raises(DataConflictError):
        asyncio.run(bag.write(key, value, "stage_b"))

# Event sequencing
@given(events())
def test_event_sequence_monotonic(events):
    """Event sequences are always monotonically increasing."""
    for i in range(1, len(events)):
        assert events[i].sequence > events[i-1].sequence
```

### Contract Tests

```python
class StageContractTest:
    """Verify all stages comply with Stage protocol."""
    
    async def test_emits_started_event(self, stage: Stage, ctx: PipelineContext):
        """Stage must emit started event."""
        await stage.execute(ctx)
        events = ctx.get_events()
        assert any(e.type == f"stage.{stage.name}.started" for e in events)
    
    async def test_emits_completed_or_failed(self, stage: Stage, ctx: PipelineContext):
        """Stage must emit completed or failed event."""
        try:
            await stage.execute(ctx)
            events = ctx.get_events()
            assert any(e.type == f"stage.{stage.name}.completed" for e in events)
        except Exception:
            events = ctx.get_events()
            assert any(e.type == f"stage.{stage.name}.failed" for e in events)
    
    async def test_returns_stage_output(self, stage: Stage, ctx: PipelineContext):
        """Stage must return StageOutput."""
        result = await stage.execute(ctx)
        assert isinstance(result, StageOutput)
```

### Fault-Injection Tests

```python
class FaultInjectionTest:
    """Simulate provider failures and verify graceful degradation."""
    
    async def test_llm_timeout(self):
        """Pipeline handles LLM timeout gracefully."""
        with inject_fault("llm", FaultType.TIMEOUT, duration_ms=5000):
            result = await pipeline.run(ctx)
            assert result.status == "failed"
            assert "timeout" in result.error.lower()
    
    async def test_stt_error(self):
        """Pipeline handles STT error gracefully."""
        with inject_fault("stt", FaultType.ERROR, message="Service unavailable"):
            result = await pipeline.run(ctx)
            assert result.status == "failed"
            assert ctx.dlq_entry is not None
    
    async def test_circuit_breaker_opens(self):
        """Circuit breaker opens after repeated failures."""
        for _ in range(5):
            with inject_fault("llm", FaultType.ERROR):
                await pipeline.run(ctx)
        
        # Next call should be short-circuited
        result = await pipeline.run(ctx)
        assert "circuit breaker open" in result.error.lower()
```

### Benchmark Suite

```python
@pytest.mark.benchmark
class PipelineBenchmarks:
    """Performance benchmarks for substrate operations."""
    
    def test_pipeline_build_time(self, benchmark):
        """Pipeline.build() must complete in <10ms."""
        pipeline = create_test_pipeline()
        result = benchmark(pipeline.build)
        assert result.stats.median < 0.010  # 10ms
    
    def test_context_bag_throughput(self, benchmark):
        """ContextBag must handle >10k writes/sec."""
        bag = ContextBag()
        def write_many():
            for i in range(1000):
                asyncio.run(bag.write(f"key_{i}", "value", "stage"))
        
        result = benchmark(write_many)
        ops_per_sec = 1000 / result.stats.median
        assert ops_per_sec > 10000
    
    def test_voice_pipeline_latency(self, benchmark):
        """Voice pipeline P50 must be <500ms."""
        result = benchmark(run_voice_pipeline)
        assert result.stats.median < 0.500  # 500ms
```

---

## 🧩 Parallelization Plan (A/B/C)

### Worker A (Property Tests)
- **Task 1.1:** Create Hypothesis strategies for stages, pipelines, events
- **Task 1.2:** Implement DAG validity property tests
- **Task 1.3:** Implement composition property tests
- **Task 1.4:** Implement ContextBag property tests

### Worker B (Contract + Fault Tests)
- **Task 2.1:** Create StageContractTest base class
- **Task 2.2:** Implement contract tests for all existing stages
- **Task 2.3:** Create fault injection framework
- **Task 2.4:** Implement fault-injection tests

### Worker C (Benchmarks + Central Pulse)
- **Task 3.1:** Set up pytest-benchmark integration
- **Task 3.2:** Create benchmark suite
- **Task 3.3:** Create Central Pulse dashboard for trends
- **Task 3.4:** Set up benchmark gates in CI

---

## ✅ Detailed Task List

### Setup & Infrastructure
- [ ] **Task 0.1: Set up testing infrastructure**
  - [ ] Verify `pytest` and `pytest-asyncio` are in dev dependencies
  - [ ] Add `hypothesis` to dev dependencies for property-based testing
  - [ ] Add `pytest-benchmark` to dev dependencies
  - [ ] Create `tests/property/` directory for property tests
  - [ ] Create `tests/contract/` directory for contract tests
  - [ ] Create `tests/fault/` directory for fault injection tests
  - [ ] Create `tests/benchmarks/` directory for benchmarks

- [ ] **Task 0.2: Create test utilities module**
  - [ ] Create `tests/utils/__init__.py`
  - [ ] Create `tests/utils/factories.py` for test data factories
  - [ ] Create `tests/utils/mocks.py` for common mocks
  - [ ] Create `tests/utils/assertions.py` for custom assertions

### Hypothesis Strategies (Worker A)
- [ ] **Task 1.1: Create Hypothesis strategies for stages**
  - [ ] Create file `tests/property/strategies.py`
  - [ ] Define `stage_names()` strategy for valid stage names
  - [ ] Define `stage_specs()` strategy for PipelineSpec objects
  - [ ] Define `dependencies()` strategy for valid dependency lists
  - [ ] Ensure generated specs don't have self-dependencies

- [ ] **Task 1.2: Create Hypothesis strategies for pipelines**
  - [ ] Define `pipelines()` strategy for Pipeline objects
  - [ ] Ensure generated pipelines are valid (no cycles)
  - [ ] Add `@composite` decorator for complex generation
  - [ ] Define `pipeline_pairs()` for composition testing

- [ ] **Task 1.3: Create Hypothesis strategies for events**
  - [ ] Define `events()` strategy for pipeline events
  - [ ] Define `event_sequences()` strategy for ordered event lists
  - [ ] Ensure sequences have monotonic sequence numbers

- [ ] **Task 1.4: Create Hypothesis strategies for context**
  - [ ] Define `context_keys()` strategy for valid keys
  - [ ] Define `context_values()` strategy for serializable values
  - [ ] Define `context_bags()` strategy for ContextBag objects

### Property-Based Tests (Worker A)
- [ ] **Task 2.1: DAG no-cycles property test**
  - [ ] Create file `tests/property/test_dag_properties.py`
  - [ ] Test: any generated Pipeline has no cycles
  - [ ] Test: Pipeline.build() always produces valid StageGraph
  - [ ] Test: topological sort is always possible
  - [ ] Use `@given(stage_specs())` decorator

- [ ] **Task 2.2: Composition associativity test**
  - [ ] Create file `tests/property/test_composition_properties.py`
  - [ ] Test: `(a.compose(b)).compose(c) == a.compose(b.compose(c))`
  - [ ] Test: `a.compose(a) == a` (idempotent for same pipeline)
  - [ ] Test: composition preserves all stages from both pipelines
  - [ ] Use `@given(pipelines(), pipelines(), pipelines())` decorator

- [ ] **Task 2.3: ContextBag conflict detection test**
  - [ ] Create file `tests/property/test_context_bag_properties.py`
  - [ ] Test: writing same key twice always raises DataConflictError
  - [ ] Test: writing different keys never raises
  - [ ] Test: read after write always returns written value
  - [ ] Use `@given(context_keys(), context_values())` decorator

- [ ] **Task 2.4: Event sequence monotonicity test**
  - [ ] Create file `tests/property/test_event_properties.py`
  - [ ] Test: event sequences are always monotonically increasing
  - [ ] Test: no duplicate sequence numbers in a run
  - [ ] Test: sequence numbers start from 1
  - [ ] Use `@given(event_sequences())` decorator

### Contract Tests (Worker B)
- [ ] **Task 3.1: Create StageContractTest base class**
  - [ ] Create file `tests/contract/base.py`
  - [ ] Define `StageContractTest` class with common setup
  - [ ] Add `create_test_context()` helper method
  - [ ] Add `get_emitted_events()` helper method
  - [ ] Add `assert_event_emitted(event_type)` helper method

- [ ] **Task 3.2: Implement started event contract test**
  - [ ] Create file `tests/contract/test_stage_contracts.py`
  - [ ] Test: every stage emits `stage.{name}.started` event
  - [ ] Test: started event includes `pipeline_run_id`
  - [ ] Test: started event includes `timestamp`
  - [ ] Parametrize test for all registered stages

- [ ] **Task 3.3: Implement completed/failed event contract test**
  - [ ] Test: every stage emits either `stage.{name}.completed` or `stage.{name}.failed`
  - [ ] Test: completed event includes `duration_ms`
  - [ ] Test: failed event includes `error_code` and `error_message`
  - [ ] Test: exactly one terminal event per execution

- [ ] **Task 3.4: Implement StageOutput contract test**
  - [ ] Test: every stage returns `StageOutput` instance
  - [ ] Test: StageOutput has valid `status` field
  - [ ] Test: StageOutput `outputs` match declared outputs
  - [ ] Test: StageOutput is serializable

- [ ] **Task 3.5: Create stage discovery for contract tests**
  - [ ] Create `get_all_stages()` function to discover stages
  - [ ] Use pytest parametrize to run contracts on all stages
  - [ ] Skip stages marked as `@skip_contract_tests`

### Fault Injection Framework (Worker B)
- [ ] **Task 4.1: Create fault injection context manager**
  - [ ] Create file `tests/fault/injection.py`
  - [ ] Define `FaultType` enum: `TIMEOUT`, `ERROR`, `SLOW`, `INTERMITTENT`
  - [ ] Define `inject_fault(provider, fault_type, **kwargs)` context manager
  - [ ] Store original provider behavior and restore on exit
  - [ ] Support nested fault injection

- [ ] **Task 4.2: Implement provider fault injection**
  - [ ] Create `FaultInjector` class for each provider type
  - [ ] `LlmFaultInjector`: timeout, error, slow response
  - [ ] `SttFaultInjector`: timeout, error, empty transcript
  - [ ] `TtsFaultInjector`: timeout, error, invalid audio
  - [ ] `DbFaultInjector`: connection error, timeout

- [ ] **Task 4.3: LLM timeout fault test**
  - [ ] Create file `tests/fault/test_llm_faults.py`
  - [ ] Test: pipeline handles LLM timeout gracefully
  - [ ] Test: timeout error is logged with context
  - [ ] Test: pipeline status is "failed" after timeout
  - [ ] Test: appropriate error event is emitted

- [ ] **Task 4.4: STT error fault test**
  - [ ] Create file `tests/fault/test_stt_faults.py`
  - [ ] Test: pipeline handles STT error gracefully
  - [ ] Test: DLQ entry created for STT failure
  - [ ] Test: user receives appropriate error message

- [ ] **Task 4.5: Circuit breaker fault test**
  - [ ] Create file `tests/fault/test_circuit_breaker.py`
  - [ ] Test: circuit breaker opens after N failures
  - [ ] Test: requests fail-fast when circuit is open
  - [ ] Test: circuit breaker half-opens after timeout
  - [ ] Test: circuit breaker closes after successful probe

### Benchmark Suite (Worker C)
- [ ] **Task 5.1: Set up pytest-benchmark**
  - [ ] Add `pytest-benchmark` configuration to `pyproject.toml`
  - [ ] Create `tests/benchmarks/conftest.py` with fixtures
  - [ ] Configure benchmark output format (JSON for CI)
  - [ ] Set up benchmark comparison baseline

- [ ] **Task 5.2: Pipeline build benchmark**
  - [ ] Create file `tests/benchmarks/test_pipeline_benchmarks.py`
  - [ ] Benchmark: simple pipeline (3 stages) build time
  - [ ] Benchmark: medium pipeline (10 stages) build time
  - [ ] Benchmark: complex pipeline (20 stages with deps) build time
  - [ ] Assert: complex pipeline <10ms P50

- [ ] **Task 5.3: ContextBag throughput benchmark**
  - [ ] Create file `tests/benchmarks/test_context_bag_benchmarks.py`
  - [ ] Benchmark: sequential writes (10k operations)
  - [ ] Benchmark: concurrent writes (10k ops, 10 tasks)
  - [ ] Benchmark: read throughput (100k reads)
  - [ ] Assert: >10k writes/sec

- [ ] **Task 5.4: Voice pipeline latency benchmark**
  - [ ] Create file `tests/benchmarks/test_pipeline_latency_benchmarks.py`
  - [ ] Benchmark: voice pipeline end-to-end (mocked providers)
  - [ ] Benchmark: chat pipeline end-to-end (mocked providers)
  - [ ] Measure P50, P95, P99 latencies
  - [ ] Assert: voice P50 <500ms, chat P50 <300ms

- [ ] **Task 5.5: Stage latency benchmarks**
  - [ ] Benchmark: individual stage execution times
  - [ ] Benchmark: interceptor overhead
  - [ ] Benchmark: event emission overhead
  - [ ] Identify stages that exceed budget

### Central Pulse Dashboard (Worker C)
- [ ] **Task 6.1: Create benchmark results storage**
  - [ ] Define schema for benchmark results
  - [ ] Store results with timestamp and git commit
  - [ ] Support historical comparison

- [ ] **Task 6.2: Create Central Pulse dashboard**
  - [ ] Create dashboard for pipeline build time trend
  - [ ] Create dashboard for stage latency distribution
  - [ ] Create dashboard for error rate by stage
  - [ ] Create dashboard for circuit breaker state changes

- [ ] **Task 6.3: Set up alerting**
  - [ ] Alert if P99 latency exceeds budget for 5 minutes
  - [ ] Alert if error rate >1% for 5 minutes
  - [ ] Alert if benchmark regresses >20%
  - [ ] Configure alert destinations (Slack, email)

### CI Integration
- [ ] **Task 7.1: Add property tests to CI**
  - [ ] Add property test step to CI workflow
  - [ ] Run with `--hypothesis-seed` for reproducibility
  - [ ] Set max examples for CI (lower than local)
  - [ ] Fail build on property test failure

- [ ] **Task 7.2: Add contract tests to CI**
  - [ ] Add contract test step to CI workflow
  - [ ] Run after unit tests, before integration tests
  - [ ] Fail build on contract violation

- [ ] **Task 7.3: Add benchmark gates to CI**
  - [ ] Add benchmark step to CI workflow
  - [ ] Compare against baseline (previous main branch)
  - [ ] Fail build if regression >10%
  - [ ] Store results for trending

- [ ] **Task 7.4: Create nightly test job**
  - [ ] Run full property test suite (more examples)
  - [ ] Run load tests
  - [ ] Run extended fault injection tests
  - [ ] Report results to Central Pulse

### Documentation
- [ ] **Task 8.1: Document testing strategy**
  - [ ] Add "Testing Strategy" section to ARCHITECTURE.md
  - [ ] Document test pyramid and coverage targets
  - [ ] Document property-based testing approach
  - [ ] Document contract testing approach

- [ ] **Task 8.2: Create testing guide**
  - [ ] Create `docs/guides/testing.md`
  - [ ] Document how to write property tests
  - [ ] Document how to write contract tests
  - [ ] Document how to use fault injection
  - [ ] Document benchmark development

---

## 🔍 Test Plan

### Test Coverage Targets

| Component | Target |
|-----------|--------|
| StageGraph | 100% |
| Pipeline | 100% |
| ContextBag | 100% |
| PipelineOrchestrator | 95% |
| Interceptors | 95% |

### Benchmark Targets

| Metric | P50 Target | P99 Target | Gate |
|--------|------------|------------|------|
| Pipeline build | <10ms | <50ms | Pre-merge |
| ContextBag write | <0.1ms | <1ms | Pre-merge |
| Voice pipeline | <500ms | <1000ms | Nightly |
| Chat pipeline | <300ms | <800ms | Nightly |

---

## 👁️ Observability Checklist

### Central Pulse Dashboard
- [ ] Pipeline build time trend
- [ ] Stage latency distribution
- [ ] Error rate by stage
- [ ] Circuit breaker state changes

### Alerting
- [ ] Alert if P99 latency exceeds budget for 5min
- [ ] Alert if error rate >1% for 5min
- [ ] Alert if benchmark regresses >20%

---

## ✔️ Completion Checklist

- [ ] Property-based tests implemented
- [ ] Contract tests for all stages
- [ ] Fault-injection tests working
- [ ] Benchmark suite complete
- [ ] Central Pulse dashboard live
- [ ] CI gates enforcing budgets

---

## 🔗 Related Documents

- [stageflow2.md](./stageflow2.md) §14 Testing Strategy
- [MASTER-ROADMAP.md](../MASTER-ROADMAP.md)
