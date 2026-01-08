# STF-REC-001: Stageflow Generalization Audit & Recommendations

**Status:** Draft  
**Created:** 2026-01-08  
**Based on:** Analysis of to-do.txt concerns and codebase investigation

---

## Executive Summary

This document provides a comprehensive analysis of the stageflow framework's current state and recommendations for generalizing it from its Eloquence-specific origins into a reusable, SOLID-compliant pipeline framework suitable for any organization or builder.

---

## 1. Eloquence-Specific Code Removal

### 1.1 Skills & Assessment (HIGH PRIORITY)

**Current State:**
- `SkillsEnrichment` in `@/home/antonio/programming/stageflow/stageflow/context/enrichments.py:30-36` contains Eloquence-specific fields:
  - `active_skill_ids`, `current_level`, `skill_progress`
- `ContextSnapshot` in `@/home/antonio/programming/stageflow/stageflow/context/context_snapshot.py:60-66` has:
  - `skills: SkillsEnrichment | None`
  - `exercise_id: str | None`
  - `assessment_state: dict[str, Any]`
- `ProfileEnrichment` has `skill_levels: dict[str, str]` field
- `skip_assessment` logic in `@/home/antonio/programming/stageflow/stageflow/pipeline/dag.py:177-201`

**Recommendation:**
1. **Remove** `SkillsEnrichment` entirely from core enrichments
2. **Remove** `exercise_id` and `assessment_state` from `ContextSnapshot`
3. **Remove** `skill_levels` from `ProfileEnrichment`
4. **Replace with** a generic `extensions: dict[str, Any]` field on `ContextSnapshot` for app-specific data
5. **Create** a `TypedExtension` protocol pattern for type-safe extensions:

```python
# In stageflow/context/extensions.py (NEW)
from typing import Protocol, TypeVar, Any

T = TypeVar("T")

class TypedExtension(Protocol[T]):
    """Protocol for type-safe context extensions."""
    key: str
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T: ...
    def to_dict(self) -> dict[str, Any]: ...

# App-specific usage (in Eloquence, not stageflow):
@dataclass
class SkillsExtension:
    key: str = "skills"
    active_skill_ids: list[str] = field(default_factory=list)
    # ... etc
```

### 1.2 Channel & Topology (MEDIUM PRIORITY)

**Current State:**
- `channel` and `topology` appear 65+ times across 9 files
- Used in `ContextSnapshot`, `PipelineContext`, `InterceptorContext`
- `extract_quality_mode()` derives "fast/balanced/accurate" from topology strings
- Hardcoded topology patterns like `"chat_fast"`, `"voice_accurate"`, `"fast_kernel"`

**Recommendation:**
1. **Keep** `topology` as a generic string identifier for pipeline selection
2. **Rename** `channel` → `transport` (more generic: "websocket", "http", "grpc")
3. **Remove** `extract_quality_mode()` from core - this is app-specific logic
4. **Create** a `PipelineMetadata` protocol for app-specific topology interpretation:

```python
# In stageflow/pipeline/metadata.py (NEW)
class PipelineMetadata(Protocol):
    """Protocol for interpreting pipeline topology."""
    
    def get_service(self, topology: str) -> str | None: ...
    def get_mode(self, topology: str) -> str | None: ...
    def get_transport(self, topology: str) -> str | None: ...
```

### 1.3 Quality Mode (HIGH PRIORITY - REMOVE)

**Current State:**
- `quality_mode` property in `@/home/antonio/programming/stageflow/stageflow/pipeline/interceptors.py:106-118`
- `extract_quality_mode()` in `@/home/antonio/programming/stageflow/stageflow/stages/context.py:40-62`
- References to "fast", "balanced", "accurate", "practice" modes
- `PolicyContext.quality_mode` field

**Recommendation:**
1. **Delete** `quality_mode` property from `InterceptorContext`
2. **Delete** `extract_quality_mode()` function
3. **Remove** quality_mode from `PolicyContext`
4. Applications that need quality modes should handle this in their own layer

### 1.4 Behavior Field (KEEP - Generic Enough)

**Current State:**
- `behavior: str | None` in `ContextSnapshot`, `PipelineContext`
- Used for "practice", "roleplay", "doc_edit" etc.

**Recommendation:**
- **Keep** this field - it's generic enough as a string
- Document that it's application-defined
- Consider renaming to `mode` or `execution_mode` for clarity

---

## 2. Code Organization Audit

### 2.1 Duplicate DAG Implementations (HIGH PRIORITY)

**Current State:**
- `@/home/antonio/programming/stageflow/stageflow/stages/graph.py` - `UnifiedStageGraph` (465 lines)
- `@/home/antonio/programming/stageflow/stageflow/pipeline/dag.py` - `StageGraph` (304 lines)

**Analysis:**
| Feature | UnifiedStageGraph | StageGraph |
|---------|-------------------|------------|
| Context Type | `StageContext` | `PipelineContext` |
| Result Type | `StageOutput` | `StageResult` |
| Interceptors | No | Yes |
| Cancellation | Via StageStatus.CANCEL | Via ctx.canceled flag |
| Location | stages/ | pipeline/ |

**Recommendation:**
1. **Consolidate** into single implementation in `pipeline/dag.py`
2. **Migrate** to `StageContext`/`StageOutput` (newer protocol)
3. **Keep** interceptor support from `StageGraph`
4. **Delete** `stages/graph.py` after migration
5. **Create** adapter for legacy code during transition

### 2.2 Duplicate Ports Definitions (MEDIUM PRIORITY)

**Current State:**
- `@/home/antonio/programming/stageflow/stageflow/ports.py` - Protocol definitions (`EventSink`, `RunStore`, `ConfigProvider`, `CorrelationIds`)
- `@/home/antonio/programming/stageflow/stageflow/stages/ports.py` - Runtime capabilities (`StagePorts` with db, callbacks, providers)

**Analysis:**
These serve **different purposes**:
- Root `ports.py`: Infrastructure protocols (DIP compliance)
- `stages/ports.py`: Stage runtime capabilities (callbacks, services)

**Recommendation:**
1. **Rename** root `ports.py` → `protocols.py` (clearer intent)
2. **Keep** `stages/ports.py` as-is but rename to `stages/capabilities.py`
3. **Document** the distinction clearly

### 2.3 Stages Module Organization (MEDIUM PRIORITY)

**Current State:**
`stageflow/stages/` contains:
- `agent.py` (626 lines) - Tool registry, executor, action types
- `context.py` (163 lines) - PipelineContext
- `errors.py` (large) - Error handling
- `graph.py` (465 lines) - UnifiedStageGraph (DUPLICATE)
- `inputs.py` - Stage inputs
- `orchestrator.py` (large) - Orchestration logic
- `ports.py` - StagePorts
- `result.py` - StageResult

**Issues:**
1. `agent.py` imports from `app.ai.framework.*` (Eloquence-specific!)
2. `graph.py` duplicates `pipeline/dag.py`
3. `context.py` here vs `context/` package confusion

**Recommendation - New Structure:**
```
stageflow/
├── core/                    # Core types (KEEP)
│   ├── stage_protocol.py
│   ├── stage_context.py
│   ├── stage_output.py
│   ├── stage_enums.py
│   └── timer.py
├── context/                 # Context management (KEEP)
│   ├── context_snapshot.py
│   ├── enrichments.py       # Make generic
│   ├── extensions.py        # NEW - typed extension protocol
│   └── types.py
├── pipeline/                # Pipeline execution (CONSOLIDATE HERE)
│   ├── dag.py              # Single DAG executor
│   ├── builder.py
│   ├── interceptors.py
│   ├── spec.py
│   └── registry.py
├── protocols.py             # RENAMED from ports.py
├── capabilities.py          # MOVED from stages/ports.py
└── execution/               # Runtime execution
    ├── inputs.py            # MOVED from stages/
    └── results.py           # MOVED from stages/
```

**DELETE or MOVE to app layer:**
- `stages/agent.py` → Move to Eloquence (has app imports)
- `stages/graph.py` → Delete (consolidated into pipeline/dag.py)
- `stages/orchestrator.py` → Evaluate if generic enough
- `stages/context.py` → Merge into core/stage_context.py

NOTE: use cp, do not try to rewrite files.
---

## 3. Observability Concerns

### 3.1 Application-Specific Observability (HIGH PRIORITY)

**Current State:**
`@/home/antonio/programming/stageflow/stageflow/observability/observability.py` (2112 lines!) contains:
- Direct imports from `app.config`, `app.models`, `app.ai.framework.*`
- `ProviderCall` database model usage
- SQLAlchemy session handling
- Circuit breaker with app-specific settings

**This file is 100% Eloquence-specific and should NOT be in stageflow.**

**Recommendation:**
1. **Move entire file** to Eloquence application layer
2. **Create** generic observability protocols in stageflow:

```python
# stageflow/observability/protocols.py (NEW)
from typing import Protocol, Any
from uuid import UUID

class ProviderCallLogger(Protocol):
    """Protocol for logging provider API calls."""
    
    async def log_call_start(
        self,
        *,
        operation: str,
        provider: str,
        model_id: str | None,
        **context: Any,
    ) -> UUID: ...
    
    async def log_call_end(
        self,
        call_id: UUID,
        *,
        success: bool,
        latency_ms: int,
        error: str | None = None,
        **metrics: Any,
    ) -> None: ...

class CircuitBreaker(Protocol):
    """Protocol for circuit breaker pattern."""
    
    async def is_open(self, *, operation: str, provider: str) -> bool: ...
    async def record_success(self, *, operation: str, provider: str) -> None: ...
    async def record_failure(self, *, operation: str, provider: str, reason: str) -> None: ...
```

### 3.2 WebSocket Projector (MEDIUM PRIORITY)

**Current State:**
`@/home/antonio/programming/stageflow/stageflow/projector/service.py` - WebSocket-specific message projection

**Analysis:**
- Assumes WebSocket transport
- What about HTTP SSE? gRPC streaming? Message queues?

**Recommendation:**
1. **Rename** to `ws_projector.py` (be explicit about WS)
2. **Create** generic `MessageProjector` protocol:

```python
# stageflow/projector/protocols.py (NEW)
class MessageProjector(Protocol):
    """Protocol for projecting pipeline events to clients."""
    
    def project(
        self,
        message: dict[str, Any],
        *,
        connection_context: dict[str, Any],
    ) -> dict[str, Any]: ...
```

3. **Document** that `WSMessageProjector` is one implementation
4. Applications can implement their own (SSE, gRPC, etc.)

### 3.3 Wide Events Question

**From to-do:** "are we using wide events? should we?"

**Analysis:**
Wide events (single event with all context) vs. narrow events (many small events) is a observability pattern choice.

**Current state:** Mixed - some wide events in stage completion, some narrow in interceptors.

**Recommendation:**
1. **Define** event schema standard in docs
2. **Prefer** wide events for pipeline observability (easier correlation)
3. **Create** `EventSchema` protocol:

```python
# stageflow/events/schema.py (NEW)
@dataclass
class PipelineEvent:
    """Standard wide event for pipeline observability."""
    
    # Identity (always present)
    event_id: UUID
    event_type: str
    timestamp: datetime
    
    # Correlation (propagated)
    pipeline_run_id: UUID | None
    request_id: UUID | None
    session_id: UUID | None
    user_id: UUID | None
    org_id: UUID | None
    
    # Context (event-specific)
    stage: str | None = None
    status: str | None = None
    duration_ms: int | None = None
    
    # Payload (flexible)
    data: dict[str, Any] = field(default_factory=dict)
```

---

## 4. Extension Points for Builders

### 4.1 Generic Extension System

To replace Eloquence-specific features (skills, assessment, quality_mode) while keeping flexibility:

```python
# stageflow/extensions/registry.py (NEW)
from typing import TypeVar, Generic, Any

T = TypeVar("T")

class ExtensionRegistry:
    """Registry for application-specific extensions."""
    
    _extensions: dict[str, type] = {}
    
    @classmethod
    def register(cls, key: str, extension_type: type) -> None:
        cls._extensions[key] = extension_type
    
    @classmethod
    def get(cls, key: str) -> type | None:
        return cls._extensions.get(key)

# Usage in Eloquence:
@dataclass
class SkillsExtension:
    active_skill_ids: list[str]
    current_level: str | None
    
ExtensionRegistry.register("skills", SkillsExtension)

# In ContextSnapshot:
extensions: dict[str, Any] = field(default_factory=dict)

def get_extension(self, key: str, ext_type: type[T]) -> T | None:
    data = self.extensions.get(key)
    if data is None:
        return None
    return ext_type(**data) if isinstance(data, dict) else data
```

### 4.2 Organization/Builder Customization Points

| Extension Point | Protocol | Purpose |
|-----------------|----------|---------|
| `PipelineMetadata` | Interpret topology strings | App-specific routing |
| `EnrichmentProvider` | Add context to snapshot | Profile, memory, etc. |
| `PolicyEvaluator` | Gate stage execution | Auth, rate limiting |
| `EventEmitter` | Emit observability events | Logging, metrics |
| `MessageProjector` | Transform outbound messages | WS, SSE, gRPC |
| `ProviderCallLogger` | Log external API calls | Cost tracking, debugging |

---

## 5. Stage Output Types Question

**From to-do:** "do we need to have specific stage output types for different kinds of stages like AGENT, WORK, ENRICH?"

**Current State:**
- `StageKind` enum: TRANSFORM, ENRICH, ROUTE, GUARD, WORK, AGENT
- Single `StageOutput` type for all stages

**Analysis:**
Generic `StageOutput` is **correct** for the framework level. Reasons:
1. Keeps pipeline executor simple
2. Allows uniform interceptor handling
3. Type-specific data goes in `data: dict[str, Any]`

**Recommendation:**
1. **Keep** single `StageOutput` type
2. **Document** conventions for each `StageKind`:

```python
# Documentation for stage output conventions:

# TRANSFORM stages (STT, TTS, LLM):
# data = {"text": str, "tokens": int, "audio_chunks": list[bytes]}

# ENRICH stages (Profile, Memory):
# data = {"profile": ProfileEnrichment, "memory": MemoryEnrichment}

# ROUTE stages (Router):
# data = {"selected_pipeline": str, "reason": str}

# GUARD stages (Guardrails):
# data = {"passed": bool, "violations": list[str]}

# WORK stages (Persist, Assessment):
# data = {"persisted_ids": list[UUID], "side_effects": list[str]}

# AGENT stages (Coach):
# data = {"response": str, "actions": list[Action], "artifacts": list[Artifact]}
```

3. **Create** optional typed result helpers (not required):

```python
# stageflow/results/typed.py (OPTIONAL)
@dataclass
class TransformResult:
    """Typed result for TRANSFORM stages."""
    text: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    
    def to_stage_output(self) -> StageOutput:
        return StageOutput.ok(data=asdict(self))
```

---

## 6. Implementation Priority

### Phase 1: Critical Cleanup (Week 1-2)
1. ☐ Move `observability/observability.py` to Eloquence
2. ☐ Delete `stages/graph.py` (consolidate to `pipeline/dag.py`)
3. ☐ Remove `quality_mode` from interceptors and context
4. ☐ Remove `skip_assessment` logic from DAG

### Phase 2: Generalization (Week 3-4)
1. ☐ Remove `SkillsEnrichment` from core
2. ☐ Remove `exercise_id`, `assessment_state` from ContextSnapshot
3. ☐ Add generic `extensions: dict[str, Any]` field
4. ☐ Create extension protocol and registry
5. ☐ Rename `ports.py` → `protocols.py`

### Phase 3: Organization (Week 5-6)
1. ☐ Move `stages/agent.py` to Eloquence (has app imports)
2. ☐ Reorganize directory structure per Section 2.3
3. ☐ Create observability protocols
4. ☐ Create projector protocols
5. ☐ Document extension points

### Phase 4: Documentation (Week 7)
1. ☐ Document StageKind output conventions
2. ☐ Document extension system
3. ☐ Create "Building with Stageflow" guide
4. ☐ Create migration guide for Eloquence

---

## 7. SOLID Compliance Checklist

| Principle | Current State | Recommendation |
|-----------|---------------|----------------|
| **S**ingle Responsibility | ❌ observability.py does too much | Split into protocols + app implementation |
| **O**pen/Closed | ⚠️ Limited extension points | Add extension registry |
| **L**iskov Substitution | ✅ Protocols allow substitution | Maintain |
| **I**nterface Segregation | ⚠️ StagePorts has too many fields | Consider splitting by concern |
| **D**ependency Inversion | ❌ Direct app imports in stages/agent.py | Move to app layer |

---

## 8. Files to Delete/Move Summary

### Delete from Stageflow:
- `stageflow/stages/graph.py` (after consolidation)

### Move to Eloquence Application:
- `stageflow/observability/observability.py` (entire file)
- `stageflow/stages/agent.py` (has `app.*` imports)

### Rename:
- `stageflow/ports.py` → `stageflow/protocols.py`
- `stageflow/stages/ports.py` → `stageflow/capabilities.py`
- `stageflow/projector/service.py` → `stageflow/projector/ws_projector.py`

---

## Appendix A: Grep Results Summary

| Pattern | Occurrences | Files |
|---------|-------------|-------|
| `skill\|assessment\|topic\|quality_mode` | 54 | 15 |
| `channel\|topology` | 65 | 9 |
| `from app.` imports | ~20 | 3 |
| `SkillsEnrichment` | 6 | 3 |
| `quality_mode` | 4 | 3 |

---

## Appendix B: Key Files Reference

| File | Lines | Purpose | Action |
|------|-------|---------|--------|
| `pipeline/dag.py` | 304 | DAG executor | Keep, enhance |
| `stages/graph.py` | 465 | Unified DAG | Delete (duplicate) |
| `observability/observability.py` | 2112 | Provider logging | Move to app |
| `stages/agent.py` | 626 | Tool system | Move to app |
| `context/enrichments.py` | 47 | Enrichment types | Generalize |
| `context/context_snapshot.py` | 248 | Immutable snapshot | Remove app-specific fields |
| `pipeline/interceptors.py` | 526 | Middleware | Remove quality_mode |
