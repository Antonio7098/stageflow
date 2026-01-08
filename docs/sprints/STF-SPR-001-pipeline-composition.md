# STF-SPR-001: Pipeline Composition + ContextBag

**Status:** 🟢 Complete  
**Branch:** `feature/stf-spr-001-pipeline-composition`  
**Duration:** 1 week  
**Dependencies:** STF-SPR-000 (Generalization)

---

## 📅 Sprint Details & Goals

### Overview
Enhance Pipeline builder with composition capabilities and implement ContextBag with conflict detection for safe parallel stage execution.

### Primary Goal (Must-Have)
- **Pipeline.compose(other)** merges two pipelines
- **ContextBag prevents duplicate key writes during parallel stage execution**
- **Pipeline.build() generates executable StageGraph**

### Success Criteria
- [x] `Pipeline.compose()` merges stages correctly
- [x] `Pipeline.build()` generates executable `StageGraph`
- [x] `ContextBag` detects and rejects duplicate key writes
- [x] Unit tests for composition, conflict detection pass
- [x] Benchmark: pipeline build <10ms P50

---

## 🏗️ Architecture & Design

### Pipeline Class Design

```python
@dataclass
class PipelineSpec:
    """Specification for a pipeline stage."""
    name: str
    runner: StageRunner
    dependencies: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    conditional: bool = False
    args: dict[str, Any] = field(default_factory=dict)


class Pipeline:
    """Code-defined pipeline with typed composition."""
    
    name: str
    stages: dict[str, PipelineSpec]
    
    def __init__(self, name: str, stages: list[PipelineSpec]):
        self.name = name
        self.stages = {s.name: s for s in stages}
        self._validate()
    
    def _validate(self) -> None:
        """Ensure DAG validity: all dependencies exist, no cycles."""
        ...
    
    def compose(self, other: 'Pipeline') -> 'Pipeline':
        """Merge stages from another pipeline, resolving dependencies."""
        ...
    
    def build(self) -> StageGraph:
        """Generate executable DAG for the orchestrator."""
        ...
```

### ContextBag Design

```python
class ContextBag:
    """Thread-safe output bag with conflict detection."""
    
    def __init__(self):
        self._data: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._writers: dict[str, str] = {}  # key -> stage_name
    
    async def write(self, key: str, value: Any, stage_name: str) -> None:
        """Write a key-value pair, rejecting duplicates."""
        async with self._lock:
            if key in self._data:
                raise DataConflictError(
                    key=key,
                    existing_writer=self._writers[key],
                    new_writer=stage_name,
                )
            self._data[key] = value
            self._writers[key] = stage_name
    
    def read(self, key: str, default: Any = None) -> Any:
        """Read a value (no lock needed for reads)."""
        return self._data.get(key, default)
```

### Data Flow

```
Pipeline Definition
    │
    ├── Pipeline("voice_fast", [STT, Triage, LLM, TTS])
    │
    └── Pipeline("voice_accurate", [STT, Assessment, LLM, TTS])
           │
           ▼
    voice_fast.compose(assessment_extension)
           │
           ▼
    pipeline.build() → StageGraph
           │
           ▼
    orchestrator.run(graph, context_bag)
```

---

## 🧩 Parallelization Plan (A/B)

### Worker A (Pipeline Class)
**Owns:** Pipeline definition and composition

- **Task 1.1:** Create `PipelineSpec` dataclass
- **Task 1.2:** Create `Pipeline` class with validation
- **Task 1.3:** Implement `compose()` for pipeline merging
- **Task 1.4:** Implement `build()` to generate StageGraph
- **Task 1.5:** Unit tests for composition scenarios

**Produces:** G1 (partial)

### Worker B (ContextBag)
**Owns:** Safe parallel data access

- **Task 2.1:** Create `ContextBag` class with async lock
- **Task 2.2:** Implement `write()` with conflict detection
- **Task 2.3:** Create `DataConflictError` exception
- **Task 2.4:** Integrate ContextBag into StageGraph execution
- **Task 2.5:** Unit tests for conflict scenarios

**Produces:** G1 (partial)

### Gates

- **G1 (Pipeline Composition):**
  - [x] Worker A: Pipeline class complete
  - [x] Worker B: ContextBag integrated
  - [x] Both: Integration tests pass

---

## ✅ Detailed Task List

### Setup & Infrastructure
- [x] **Task 0.1: Create pipeline module structure**
  - [x] Verify `stageflow/pipeline/` directory exists
  - [x] Verify `stageflow/pipeline/__init__.py` has module exports
  - [x] Verify existing `StageGraph` class location in `stageflow/pipeline/dag.py`

- [x] **Task 0.2: Review existing code**
  - [x] Read `stageflow/pipeline/dag.py` to understand current StageGraph
  - [x] Read `stageflow/pipeline/pipeline.py` to understand current Pipeline
  - [x] Document any existing pipeline configuration patterns

### PipelineSpec Dataclass (Worker A)
- [x] **Task 1.1: Create PipelineSpec dataclass**
  - [x] Create file `stageflow/pipeline/spec.py`
  - [x] Define `PipelineSpec` dataclass with fields: `name`, `runner`, `dependencies`, `inputs`, `outputs`, `conditional`, `args`
  - [x] Use `tuple[str, ...]` for immutable sequences (not `list`)
  - [x] Add `__post_init__` to validate `name` is non-empty
  - [x] Add `__post_init__` to validate `dependencies` don't include self
  - [x] Add docstrings explaining each field's purpose

- [x] **Task 1.2: Create StageRunner Protocol**
  - [x] Define `StageRunner` Protocol in same file
  - [x] Require `async def execute(self, ctx: StageContext) -> StageOutput`
  - [x] This allows any Stage implementation to be used as a runner

- [x] **Task 1.3: Unit tests for PipelineSpec**
  - [x] Create file `tests/unit/pipeline/test_spec.py`
  - [x] Test PipelineSpec creation with valid data
  - [x] Test PipelineSpec rejects empty name
  - [x] Test PipelineSpec rejects self-dependency
  - [x] Test PipelineSpec is hashable (for use in sets/dicts)

### Pipeline Class (Worker A)
- [x] **Task 2.1: Create Pipeline class skeleton**
  - [x] Create file `stageflow/pipeline/builder.py`
  - [x] Define `Pipeline` class with `name: str` and `stages: dict[str, PipelineSpec]`
  - [x] Add `__init__(self, name: str, stages: list[PipelineSpec])` constructor
  - [x] Convert stages list to dict keyed by stage name
  - [x] Call `_validate()` at end of `__init__`

- [x] **Task 2.2: Implement _validate() method**
  - [x] Check all dependencies reference existing stages
  - [x] Check for cycles using topological sort (Kahn's algorithm)
  - [x] Raise `PipelineValidationError` with descriptive message on failure
  - [x] Include which stages are involved in cycle or missing

- [x] **Task 2.3: Implement compose() method**
  - [x] Add `compose(self, other: 'Pipeline') -> 'Pipeline'` method
  - [x] Merge stages from both pipelines into new dict
  - [x] Handle name conflicts: raise error if same stage name with different spec
  - [x] Return new Pipeline instance (don't mutate self)
  - [x] Validate the composed pipeline before returning

- [x] **Task 2.4: Implement build() method**
  - [x] Add `build(self) -> StageGraph` method
  - [x] Convert each PipelineSpec to StageGraph node format
  - [x] Build dependency edges from spec.dependencies
  - [x] Return configured StageGraph ready for execution

- [x] **Task 2.5: Add helper methods**
  - [x] Add `get_stage(name: str) -> PipelineSpec | None`
  - [x] Add `has_stage(name: str) -> bool`
  - [x] Add `stage_names() -> list[str]` (topologically sorted)
  - [x] Add `__repr__` for debugging

- [x] **Task 2.6: Unit tests for Pipeline class**
  - [x] Create file `tests/unit/pipeline/test_pipeline.py`
  - [x] Test Pipeline creation with valid stages
  - [x] Test Pipeline rejects missing dependency
  - [x] Test Pipeline rejects cycle (A→B→A)
  - [x] Test Pipeline rejects complex cycle (A→B→C→A)
  - [x] Test compose() merges stages correctly
  - [x] Test compose() rejects conflicting stage names
  - [x] Test build() returns valid StageGraph

### PipelineRegistry (Worker A)
- [x] **Task 3.1: Create PipelineRegistry class**
  - [x] Create file `stageflow/pipeline/registry.py`
  - [x] Define `PipelineRegistry` class with `_pipelines: dict[str, Pipeline]`
  - [x] Add `register(pipeline: Pipeline) -> None` method
  - [x] Add `get(name: str) -> Pipeline | None` method
  - [x] Add `list_names() -> list[str]` method

- [x] **Task 3.2: Add singleton pattern**
  - [x] Create module-level `_default_registry: PipelineRegistry | None`
  - [x] Add `get_default_registry() -> PipelineRegistry` function
  - [x] Add `register_pipeline(pipeline: Pipeline)` convenience function

- [x] **Task 3.3: Unit tests for PipelineRegistry**
  - [x] Create file `tests/unit/pipeline/test_registry.py`
  - [x] Test register and get pipeline
  - [x] Test get returns None for unknown name
  - [x] Test list_names returns all registered

### ContextBag (Worker B)
- [x] **Task 4.1: Create ContextBag class**
  - [x] Create file `stageflow/context/bag.py`
  - [x] Define `ContextBag` class with `_data: dict[str, Any]`
  - [x] Add `_lock: asyncio.Lock` for thread safety
  - [x] Add `_writers: dict[str, str]` to track which stage wrote each key

- [x] **Task 4.2: Implement write() method**
  - [x] Add `async def write(self, key: str, value: Any, stage_name: str) -> None`
  - [x] Acquire lock before checking/writing
  - [x] If key exists, raise `DataConflictError` with both stage names
  - [x] Store value and record writer stage name
  - [x] Release lock (use `async with self._lock:`)

- [x] **Task 4.3: Implement read() method**
  - [x] Add `def read(self, key: str, default: Any = None) -> Any`
  - [x] No lock needed for reads (dict reads are atomic in Python)
  - [x] Return value or default if key not found

- [x] **Task 4.4: Implement helper methods**
  - [x] Add `def has(self, key: str) -> bool`
  - [x] Add `def keys() -> list[str]`
  - [x] Add `def get_writer(self, key: str) -> str | None`
  - [x] Add `def to_dict() -> dict[str, Any]` for debugging

- [x] **Task 4.5: Create DataConflictError exception**
  - [x] Create file `stageflow/errors.py` if not exists
  - [x] Define `DataConflictError(Exception)` with `key`, `existing_writer`, `new_writer`
  - [x] Add `__str__` that formats a helpful error message
  - [x] Example: "Key 'user_message' already written by 'stt_stage', cannot write from 'enricher_stage'"

- [x] **Task 4.6: Unit tests for ContextBag**
  - [x] Create file `tests/unit/context/test_bag.py`
  - [x] Test write() stores value correctly
  - [x] Test read() returns stored value
  - [x] Test read() returns default for missing key
  - [x] Test write() same key twice raises DataConflictError
  - [x] Test DataConflictError contains correct stage names
  - [x] Test concurrent writes to different keys succeed

### Integration (Worker B)
- [x] **Task 5.1: Integrate ContextBag into StageGraph**
  - [x] Update `stageflow/pipeline/dag.py`
  - [x] Add `context_bag: ContextBag` parameter to `run()` method
  - [x] Pass context_bag to each stage's execute() call
  - [x] Stages write outputs to context_bag instead of returning dict

- [x] **Task 5.2: Update PipelineContext**
  - [x] Update `stageflow/stages/context.py`
  - [x] Add `bag: ContextBag` property
  - [x] Provide convenience methods: `ctx.write(key, value)`, `ctx.read(key)`
  - [x] These delegate to the underlying ContextBag

- [x] **Task 5.3: Update existing stages to use ContextBag**
  - [x] Audit existing stages for output patterns
  - [x] Update stages to use `ctx.write()` instead of return dict
  - [x] Ensure stage_name is passed correctly for conflict tracking

- [x] **Task 5.4: Integration tests**
  - [x] Create file `tests/integration/test_pipeline_context_bag.py`
  - [x] Test Pipeline.build() creates working StageGraph
  - [x] Test parallel stages write to ContextBag without conflict
  - [x] Test parallel stages writing same key raises DataConflictError
  - [x] Test full pipeline execution with real stages

### Benchmarks
- [x] **Task 6.1: Create benchmark fixtures**
  - [x] Create file `tests/benchmarks/test_pipeline_benchmark.py`
  - [x] Create fixture for simple pipeline (3 stages)
  - [x] Create fixture for complex pipeline (10 stages)

- [x] **Task 6.2: Benchmark pipeline build**
  - [x] Benchmark `Pipeline.build()` for simple pipeline
  - [x] Benchmark `Pipeline.build()` for complex pipeline
  - [x] Assert <10ms P50 for complex pipeline

- [x] **Task 6.3: Benchmark ContextBag throughput**
  - [x] Benchmark sequential writes (10k ops)
  - [x] Benchmark concurrent writes (10k ops, 10 tasks)
  - [x] Assert >10k ops/sec

### Documentation
- [x] **Task 7.1: Update ARCHITECTURE.md**
  - [x] Add "Pipeline Composition" section
  - [x] Explain Pipeline vs StageGraph relationship
  - [x] Include code examples for defining pipelines
  - [x] Document compose() patterns

- [x] **Task 7.2: Create migration guide**
  - [x] Create `docs/guides/pipeline-migration.md`
  - [x] Document how to migrate from JSON-based config
  - [x] Include before/after examples
  - [x] List breaking changes

---

## 🔍 Test Plan

### Unit Tests
| Component | Test File | Coverage |
|-----------|-----------|----------|
| PipelineSpec | `tests/unit/framework/test_pipeline_spec.py` | 100% |
| Pipeline | `tests/unit/framework/test_pipeline.py` | >90% |
| ContextBag | `tests/unit/framework/test_context_bag.py` | 100% |

### Property-Based Tests (Hypothesis)
```python
@given(pipelines())
def test_compose_associativity(a, b, c):
    """(a.compose(b)).compose(c) == a.compose(b.compose(c))"""
    assert a.compose(b).compose(c).stages == a.compose(b.compose(c)).stages

@given(st.text(), st.text())
def test_context_bag_conflict(key, value):
    """Writing same key twice raises DataConflictError."""
    bag = ContextBag()
    await bag.write(key, value, "stage_a")
    with pytest.raises(DataConflictError):
        await bag.write(key, value, "stage_b")
```

### Benchmarks (Central Pulse)
| Metric | Target | Method |
|--------|--------|--------|
| Pipeline build time | <10ms P50 | `pytest-benchmark` |
| ContextBag write throughput | >10k ops/sec | `pytest-benchmark` |

---

## 👁️ Observability Checklist

### Structured Logging
- [x] Pipeline composition logs merged stage names
- [x] ContextBag conflict logs include `key`, `existing_writer`, `new_writer`
- [x] All logs include `pipeline_run_id`, `request_id`

### Wide Events
- [x] `pipeline.composed` — when pipelines are merged
- [x] `context_bag.conflict` — when duplicate write detected

---

## ✔️ Completion Checklist

- [x] Pipeline class with compose/build methods
- [x] ContextBag with conflict detection
- [x] Integration with StageGraph
- [x] Unit tests passing
- [x] Benchmarks meet targets
- [x] Docs updated

---

## 🔗 Related Documents

- [stageflow2.md](./stageflow2.md) §7.1 Composition System
- [MASTER-ROADMAP.md](../MASTER-ROADMAP.md) — Gate G1
