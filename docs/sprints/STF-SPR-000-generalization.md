# STF-SPR-000: Stageflow Generalization & PyPI Module Setup

**Status:** 🟡 In Progress  
**Branch:** `main`  
**Duration:** 3-4 days  
**Dependencies:** None (foundational sprint)

---

## 📅 Sprint Details & Goals

### Overview
Extract stageflow from the Eloquence project into a general-purpose, framework-agnostic DAG pipeline orchestration library suitable for PyPI publication. Remove all app-specific dependencies and introduce clean abstractions (ports/protocols) for persistence, configuration, and observability.

### Primary Goal (Must-Have)
By the end of this sprint, the system must be able to:
- **Run as a standalone Python package with zero app-specific dependencies**
- **Define pipelines using the fluent Pipeline builder API**
- **Execute stage DAGs with parallel execution, cancellation, and interceptors**
- **Support pluggable persistence and event sinks via protocol interfaces**

### Secondary Goals
- [ ] Complete PyPI packaging setup (pyproject.toml, README, etc.)
- [ ] Clean module structure following Python best practices
- [ ] Type stubs and comprehensive docstrings

### Success Criteria
- [ ] `pip install -e .` works with no errors
- [ ] `from stageflow import Pipeline, Stage, StageOutput` imports successfully
- [ ] Unit tests pass without any external dependencies (DB, Redis, etc.)
- [ ] No imports from `app.*` remain in the codebase
- [ ] All protocols are properly defined for extension points

---

## 🏗️ Architecture & Design

### System Changes

**Before (Eloquence-coupled):**
```
app.ai.framework
├── Tight coupling to app.database, app.models, app.config
├── SQLAlchemy-specific event sinks
├── Eloquence-specific context vars
└── Mixed domain logic (profiles, skills, exercises)
```

**After (Generic stageflow):**
```
stageflow/
├── core/           # Stage protocol, types, timer
├── graph/          # DAG executor (StageGraph, UnifiedStageGraph)
├── pipeline/       # Pipeline builder, registry
├── context/        # PipelineContext, StageContext, StageInputs
├── interceptors/   # Interceptor framework
├── events/         # EventSink protocol + NoOp implementation
├── observability/  # Logging helpers, metrics interfaces
├── errors/         # Exception hierarchy
└── ports/          # All protocol definitions (DIP)
```

### Module Dependency Graph
```
            ┌─────────────┐
            │    ports    │  ← Protocol definitions (no deps)
            └──────┬──────┘
                   │
     ┌─────────────┼─────────────┐
     │             │             │
┌────▼────┐  ┌─────▼─────┐  ┌────▼────┐
│  core   │  │  context  │  │ events  │
└────┬────┘  └─────┬─────┘  └────┬────┘
     │             │             │
     └─────────────┼─────────────┘
                   │
            ┌──────▼──────┐
            │    graph    │
            └──────┬──────┘
                   │
            ┌──────▼──────┐
            │  pipeline   │
            └──────┬──────┘
                   │
            ┌──────▼──────┐
            │interceptors │
            └─────────────┘
```

### Key Abstractions (Ports)

```python
# stageflow/ports.py

from typing import Protocol, Any
from uuid import UUID

class EventSink(Protocol):
    """Protocol for event persistence/emission."""
    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None: ...
    def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None: ...

class RunStore(Protocol):
    """Protocol for pipeline run persistence."""
    async def create_run(self, run_id: UUID, **metadata: Any) -> Any: ...
    async def update_status(self, run_id: UUID, status: str, **data: Any) -> None: ...
    async def get_run(self, run_id: UUID) -> Any | None: ...

class ConfigProvider(Protocol):
    """Protocol for configuration access."""
    def get(self, key: str, default: Any = None) -> Any: ...
```

### Correlation IDs (Generic)
```python
@dataclass(frozen=True, slots=True)
class CorrelationIds:
    """Generic correlation IDs for tracing."""
    run_id: UUID | None = None
    request_id: UUID | None = None
    trace_id: str | None = None
    # Extension point for app-specific IDs
    extra: dict[str, Any] = field(default_factory=dict)
```

---

## ✅ Task List

### G0: Project Setup
- [ ] **Task 0.1: Create pyproject.toml**
    > *Modern Python packaging with PEP 621*
    - [ ] Define package metadata (name, version, description)
    - [ ] Specify dependencies (minimal: only stdlib + typing-extensions)
    - [ ] Configure optional dependencies for testing
    - [ ] Set up entry points if needed

- [ ] **Task 0.2: Create directory structure**
    > *Clean module layout*
    - [ ] Create `stageflow/` package directory
    - [ ] Create submodule directories (core, graph, pipeline, etc.)
    - [ ] Add `__init__.py` with public API exports
    - [ ] Add `py.typed` marker for type checking

- [ ] **Task 0.3: Create README.md**
    > *Package documentation*
    - [ ] Quick start example
    - [ ] Installation instructions
    - [ ] Basic usage patterns
    - [ ] Link to full documentation

### G1: Core Protocol Extraction
- [ ] **Task 1.1: Extract ports/protocols**
    > *Define all extension point interfaces*
    - [ ] `EventSink` protocol
    - [ ] `RunStore` protocol  
    - [ ] `ConfigProvider` protocol
    - [ ] `CorrelationIds` dataclass

- [ ] **Task 1.2: Extract core stage types**
    > *Pure stage protocol with no dependencies*
    - [ ] `StageKind` enum
    - [ ] `StageStatus` enum
    - [ ] `StageOutput` dataclass
    - [ ] `StageArtifact` dataclass
    - [ ] `StageEvent` dataclass
    - [ ] `Stage` protocol
    - [ ] `PipelineTimer` class

- [ ] **Task 1.3: Extract context types**
    > *Execution context without DB dependencies*
    - [ ] `StageContext` (wraps snapshot + config)
    - [ ] `PipelineContext` (generic, no AsyncSession)
    - [ ] `StageInputs` (immutable prior outputs view)
    - [ ] `StagePorts` (generic capability injection)

### G2: Graph Executor Extraction
- [ ] **Task 2.1: Extract StageResult and errors**
    > *Result types and exception hierarchy*
    - [ ] `StageResult` dataclass
    - [ ] `StageError` base exception
    - [ ] `StageExecutionError` exception
    - [ ] `UnifiedPipelineCancelled` exception

- [ ] **Task 2.2: Extract DAG executor**
    > *Core graph execution logic*
    - [ ] `StageSpec` dataclass
    - [ ] `UnifiedStageSpec` dataclass
    - [ ] `StageGraph` class (legacy)
    - [ ] `UnifiedStageGraph` class

### G3: Pipeline Builder Extraction
- [ ] **Task 3.1: Extract Pipeline builder**
    > *Fluent API for composing stages*
    - [ ] `Pipeline` dataclass with `with_stage()`, `compose()`, `build()`
    - [ ] Remove `app.ai.framework` imports

- [ ] **Task 3.2: Extract PipelineRegistry**
    > *Registry pattern for pipeline lookup*
    - [ ] `PipelineRegistry` class
    - [ ] Remove lazy import of app-specific pipelines

### G4: Interceptor Framework Extraction
- [ ] **Task 4.1: Extract interceptor base**
    > *Middleware pattern for stages*
    - [ ] `BaseInterceptor` ABC
    - [ ] `InterceptorResult` dataclass
    - [ ] `InterceptorContext` class
    - [ ] `ErrorAction` enum
    - [ ] `run_with_interceptors()` function

- [ ] **Task 4.2: Extract built-in interceptors**
    > *Default interceptor implementations*
    - [ ] `TimeoutInterceptor`
    - [ ] `CircuitBreakerInterceptor`
    - [ ] `TracingInterceptor`
    - [ ] `MetricsInterceptor`
    - [ ] `LoggingInterceptor`
    - [ ] `get_default_interceptors()` function

### G5: Event System Extraction
- [ ] **Task 5.1: Create generic event sink**
    > *Protocol + default implementations*
    - [ ] `EventSink` protocol in ports
    - [ ] `NoOpEventSink` implementation
    - [ ] `LoggingEventSink` implementation
    - [ ] Context var management (`set_event_sink`, `get_event_sink`, `clear_event_sink`)

### G6: Remove App-Specific Code
- [ ] **Task 6.1: Remove SQLAlchemy dependencies**
    > *All DB access via ports*
    - [ ] Remove `from sqlalchemy.ext.asyncio import AsyncSession`
    - [ ] Replace `db: AsyncSession` with generic type
    - [ ] Remove `get_session_context` calls

- [ ] **Task 6.2: Remove app.config dependencies**
    > *Configuration via ConfigProvider protocol*
    - [ ] Remove `from app.config import get_settings`
    - [ ] Use `ConfigProvider` protocol instead

- [ ] **Task 6.3: Remove app.models dependencies**
    > *No ORM models in core*
    - [ ] Remove `PipelineRun`, `PipelineEvent`, `ProviderCall` imports
    - [ ] Remove `Artifact`, `OrganizationMembership` imports

- [ ] **Task 6.4: Remove app.logging_config dependencies**
    > *Generic context var approach*
    - [ ] Remove context var imports from app
    - [ ] Create stageflow-local context vars

- [ ] **Task 6.5: Fix all import paths**
    > *Change from app.ai.framework to stageflow*
    - [ ] Update all internal imports to relative or `stageflow.*`
    - [ ] Ensure no circular imports

### G7: Testing Setup
- [ ] **Task 7.1: Create test infrastructure**
    > *pytest setup with no external deps*
    - [ ] Create `tests/` directory
    - [ ] Add `conftest.py` with fixtures
    - [ ] Add test for basic pipeline execution

- [ ] **Task 7.2: Create unit tests for core**
    > *Test stage protocol and types*
    - [ ] Test `StageOutput` factory methods
    - [ ] Test `PipelineTimer`
    - [ ] Test `StageContext`

- [ ] **Task 7.3: Create integration tests**
    > *Test full pipeline execution*
    - [ ] Test simple linear pipeline
    - [ ] Test parallel stage execution
    - [ ] Test conditional stages
    - [ ] Test cancellation

### G8: Documentation & Polish
- [ ] **Task 8.1: Add module docstrings**
    > *Every module has clear purpose*
    - [ ] Update all `__init__.py` docstrings
    - [ ] Ensure all public classes have docstrings

- [ ] **Task 8.2: Create CHANGELOG.md**
    > *Track changes*
    - [ ] Initial release notes

---

## 📝 Commit Plan

Expected commits in order:

1. `chore: create pyproject.toml and package structure`
2. `refactor(ports): extract protocol definitions`
3. `refactor(core): extract stage types without app deps`
4. `refactor(context): extract context types without DB deps`
5. `refactor(graph): extract DAG executor`
6. `refactor(pipeline): extract pipeline builder`
7. `refactor(interceptors): extract interceptor framework`
8. `refactor(events): create generic event sink system`
9. `refactor: remove all app.* imports`
10. `test: add unit tests for core functionality`
11. `test: add integration tests for pipeline execution`
12. `docs: add README and module docstrings`

---

## 🔍 Test Plan

### Unit Tests
| Component | Test File | Coverage |
|-----------|-----------|----------|
| StageOutput | `tests/unit/test_stage_output.py` | >90% |
| PipelineTimer | `tests/unit/test_timer.py` | >90% |
| StageContext | `tests/unit/test_context.py` | >90% |
| Pipeline | `tests/unit/test_pipeline.py` | >90% |

### Integration Tests
| Flow | Test File | Services Mocked |
|------|-----------|-----------------|
| Linear Pipeline | `tests/integration/test_linear.py` | None |
| Parallel Pipeline | `tests/integration/test_parallel.py` | None |
| Interceptors | `tests/integration/test_interceptors.py` | None |

---

## 👁️ Observability Checklist

### Structured Logging
- [ ] All modules use `logging.getLogger(__name__)`
- [ ] No hardcoded logger names from app
- [ ] Log messages include stage names and timing

### Event Taxonomy
- [ ] `stage.{name}.started`
- [ ] `stage.{name}.completed`
- [ ] `stage.{name}.failed`
- [ ] `stage.{name}.skipped`
- [ ] `pipeline.created`
- [ ] `pipeline.started`
- [ ] `pipeline.completed`
- [ ] `pipeline.failed`
- [ ] `pipeline.cancelled`

---

## 📦 Final Package Structure

```
stageflow/
├── __init__.py              # Public API exports
├── py.typed                 # PEP 561 marker
├── ports.py                 # All protocol definitions
├── core/
│   ├── __init__.py
│   ├── stage.py             # Stage protocol, StageKind, StageStatus
│   ├── output.py            # StageOutput, StageArtifact, StageEvent
│   └── timer.py             # PipelineTimer
├── context/
│   ├── __init__.py
│   ├── pipeline.py          # PipelineContext
│   ├── stage.py             # StageContext
│   ├── inputs.py            # StageInputs
│   └── ports.py             # StagePorts
├── graph/
│   ├── __init__.py
│   ├── spec.py              # StageSpec, UnifiedStageSpec
│   ├── executor.py          # StageGraph, UnifiedStageGraph
│   └── errors.py            # StageExecutionError, etc.
├── pipeline/
│   ├── __init__.py
│   ├── builder.py           # Pipeline class
│   └── registry.py          # PipelineRegistry
├── interceptors/
│   ├── __init__.py
│   ├── base.py              # BaseInterceptor, run_with_interceptors
│   ├── timeout.py           # TimeoutInterceptor
│   ├── circuit_breaker.py   # CircuitBreakerInterceptor
│   ├── tracing.py           # TracingInterceptor
│   ├── metrics.py           # MetricsInterceptor
│   └── logging.py           # LoggingInterceptor
├── events/
│   ├── __init__.py
│   ├── sink.py              # EventSink implementations
│   └── context.py           # Context var management
└── errors.py                # Exception hierarchy

tests/
├── conftest.py
├── unit/
│   ├── test_stage_output.py
│   ├── test_timer.py
│   ├── test_context.py
│   └── test_pipeline.py
└── integration/
    ├── test_linear.py
    ├── test_parallel.py
    └── test_interceptors.py
```

---

## 📋 Notes & Decisions

### What Stays Generic
- Stage protocol and types
- DAG execution logic
- Interceptor framework
- Pipeline builder pattern
- Event taxonomy (as strings)

### What Becomes Protocol/Port
- Database access → `RunStore` protocol
- Event persistence → `EventSink` protocol
- Configuration → `ConfigProvider` protocol
- Context IDs → `CorrelationIds` dataclass (extensible)

### What Gets Removed Entirely
- `app.models.*` imports
- `app.config.get_settings`
- `app.database.get_session_context`
- `app.logging_config.*` context vars
- `app.schemas.agent_output`
- All Eloquence domain logic (profiles, skills, exercises, assessments)
- Policy gateway (moved to separate extension package)
- Observability module (heavy DB coupling - create generic version)
- Projector service (WebSocket-specific)

---

## 🔗 Related Documents

- [stageflow2.md](../stageflow2.md) - Architecture specification
- [STF-SPR-001](./STF-SPR-001-pipeline-composition.md) - Pipeline composition
- [STF-SPR-002](./STF-SPR-002-auth-tenancy-interceptors.md) - Auth interceptors
