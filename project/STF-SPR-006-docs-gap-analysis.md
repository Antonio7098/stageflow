# STF-SPR-006: Documentation Gap Remediation Plan

**Status:** Completed (full remediation Jan 9, 2026)  
**Source:** `/docs-audit.txt` (updated Jan 9, 2026)  
**Scope:** Docs + Stageflow runtime parity

---

## 1. Executive Summary

The Stageflow docs remain strong for introductory concepts but now lag behind the implementation across multiple core modules (pipeline builder, unified DAG executor, protocols, projector, tooling). These gaps materially impact new adopters, who must reverse-engineer runtime behavior, and advanced users, who lack guidance for mission-critical features (subpipelines, approvals, correlation IDs, dependency injection). This plan consolidates every gap highlighted in `docs-audit.txt` and sequences remediation workstreams so the published documentation once again mirrors the shipped APIs.

### Primary Findings

1. **API Divergence:** Stage execution signatures, PipelineContext fields, PipelineBuilder features, and AdvancedToolExecutor semantics are inconsistent between docs and code, leading to broken examples.
2. **Undocumented Modules:** Projector services, StageInputs/StagePorts, ContextBag, protocols, utilities, and registry/subpipeline helpers ship without any API references or guides.
3. **Guide Coverage Gaps:** There is no authoring guidance for StagePorts, correlation IDs, error recovery, testing, runtime deployment, or advanced interceptor patterns.
4. **Observability Blind Spots:** Subpipeline lifecycle events and correlation ID propagation are unaddressed, limiting operators’ ability to monitor child runs.
5. **Navigation / Link Rot:** Cross-references and root export listings are outdated; readers cannot map `from stageflow import …` symbols to the right page.

---

## 2. Detailed Gap Inventory

| Severity | Area | Symptom / Gap | Impact | References |
| --- | --- | --- | --- | --- |
| 🔴 Critical | Stage Interfaces | Docs still reference `run(ctx: PipelineContext)` instead of `execute(ctx: StageContext)`; no coverage of Retryable/Conditional/Observable stage interfaces. | Tutorials fail; developers implement obsolete signatures and miss orchestration hooks. | `docs-audit.txt` §1, §2.6, Stage interface contracts section |
| 🔴 Critical | Pipeline Builder & DAG | `PipelineBuilder`, `PipelineSpec.inputs/outputs`, cycle detection, `UnifiedStageGraph`, `StageInputs`, `StagePorts` undocumented; docs describe legacy `Pipeline`. | Advanced DAG composition and dataflow patterns are invisible; teams cannot leverage validation or new executor. | `docs-audit.txt` “PipelineBuilder API”, “UnifiedStageGraph”, “StageInputs”, “StagePorts” |
| 🔴 Critical | Subpipelines & Events | `SubpipelineSpawner`, `ChildRunTracker`, `SubpipelineResult`, child pipeline events totally missing. | Operators lack guidance on spawning/nesting pipelines or observing child runs. | `docs-audit.txt` “Subpipeline System” & event sections |
| 🔴 Critical | Projector / WS Streaming | `stageflow/projector` exports `WSMessageProjector` but no guide/API. | Real-time UI integrations must read source; increases support burden. | “WSMessageProjector Service” |
| 🔴 Critical | Context Model | `PipelineContext` and `ContextBag` docs lack new fields (`configuration`, `service`, parent IDs, fork/is_child_run/get_parent_data/try_emit_event`). | Users cannot wire configs, correlation IDs, or parent-child data safely. | “Context Type Ambiguity”, “ContextBag”, “PipelineContext mismatch” |
| 🟠 High | Protocols & Extensions | `ExecutionContext`, `RunStore`, `ConfigProvider`, `CorrelationIds`, `ExtensionRegistry`, `ExtensionHelper`, `TypedExtension` lack dedicated docs or examples. | Integration teams guess at lifecycle and interface requirements; extension ecosystem stalls. | Protocols + Extensions sections |
| 🟠 High | Tools System | Docs describe outdated AdvancedToolExecutor config, omit adapters/events, approval workflow details. | Tooling integrations break or miss governance hooks. | “Tool Executor Versioning”, “Advanced tool executor docs are stale”, “Tools Adapters” |
| 🟠 High | Auth / Interceptors | `auth/interceptors.py` undocumented, interceptor guide references non-exported `InterceptorContext`. | Security-sensitive logic lacks clarity; docs reference wrong symbols. | “Auth Interceptors”, “InterceptorContext reference” |
| 🟠 High | Testing & Recovery Guides | No modern testing guide leveraging `ContextSnapshot` or recovery playbooks beyond RetryableStage. | Teams cannot validate pipelines offline or design failure strategies. | “Testing Guide”, “Error Recovery Guide” |
| 🟡 Medium | Utilities & Immutability | `FrozenDict`, `FrozenList`, `extract_service()` missing API coverage; immutability story only implied. | Confusion around data guarantees, service extraction, and child pipeline isolation. | “Utility Modules”, “extract_service Utility” |
| 🟡 Medium | Navigation & Cross-Refs | Root exports (e.g., `StageResult`, `StageError`, `extract_service`, registry functions) not mapped to docs; broken links in advanced guides. | Discoverability suffers; 404s degrade trust. | “Root namespace vs docs navigation”, “Broken references” |
| 🟡 Medium | Runtime Integration & Configuration | No guidance for embedding Stageflow into FastAPI/background workers or structuring `ConfigProvider`. | Prospects question deployment readiness; inconsistent config patterns. | “Deployment & runtime integration”, “Configuration and environment management” |

---

## 3. Prioritized Remediation Backlog

| Priority | Workstream | Deliverables | Dependencies |
| --- | --- | --- | --- |
| P0 | **Stage Runtime Parity** | - Update Stage interfaces in guides/API<br>- New `docs/api/stages.md` covering StageInputs, StagePorts, StageResult vs StageOutput<br>- Add section in `guides/stages.md` on runtime helpers & interfaces | Requires code owner validation of current public surface |
| P0 | **Pipeline & Subpipeline Modernization** | - Rewrite `docs/api/pipeline.md` for PipelineBuilder, PipelineSpec, UnifiedStageGraph<br>- Extend `advanced/subpipelines.md` with spawner APIs, child run tracker, event taxonomy, payload examples<br>- Add `docs/api/events.md` section for subpipeline events | Coordinate with pipeline maintainer for canonical diagrams |
| P0 | **Context & Execution Contracts** | - Refresh `docs/api/context.md` to match PipelineContext, StageContext, ContextBag<br>- Add “Context Hierarchy” explainer tying PipelineContext → ContextSnapshot → StageContext<br>- Document `extract_service()` usage | Leverage tests under `tests/benchmarks` for examples |
| P0 | **Projector & Real-time Docs** | - New advanced guide `advanced/projector.md` describing WS projector purpose, payload schema, and integration steps<br>- API snippet for `WSMessageProjector`, `WSOutboundMessage` | Align with `test_app` usage for runnable example |
| P1 | **Protocols & Extensions** | - New `docs/api/protocols.md` and `advanced/extensions.md` refresh (ExecutionContext, RunStore, ConfigProvider, CorrelationIds, ExtensionRegistry, TypedExtension)<br>- Add infrastructure integration guide with FastAPI wiring | May require sample repo updates |
| P1 | **Tools System Refresh** | - Update tools guide/API for AdvancedToolExecutor v2 constructor, registry management, adapters, approval events<br>- Clarify ToolExecutorConfig semantics | Sync with `stageflow/tools/executor_v2.py` maintainers |
| P1 | **Observability & Correlation** | - Correlation IDs guide (propagation, best practices)<br>- Document `try_emit_event`, event sink configuration, NoOp vs Logging sinks | Coordinate with observability team |
| P2 | **Testing & Recovery Playbooks** | - Dedicated testing guide (ContextSnapshot replay, fixtures, benchmarks)<br>- Error recovery / retry strategy guide referencing RetryableStage, circuit breakers, cancellation semantics | Expand on `tests/benchmarks` and `advanced/errors.md` |
| P2 | **Navigation Polish** | - Root export index mapping `stageflow.__all__` → doc sections<br>- Fix stale links in advanced guides/interceptors<br>- Add FAQ/troubleshooting appendix | Light editorial work, can parallelize |

---

## 4. Workstream Details

### 4.1 Stage Runtime & Context
* **Docs to touch:** `docs/api/core.md`, `docs/api/context.md`, new `docs/api/stages.md`, `docs/guides/stages.md`, `docs/guides/context.md`.
* **Key actions:**
  - Replace `run(ctx: PipelineContext)` references with `execute(ctx: StageContext)` everywhere.
  - Document `StageInputs`, `StagePorts`, `StageResult`, `StageError`, and when to return `StageOutput` vs raising.
  - Expand Context hierarchy section explaining PipelineContext fields (configuration, service, parent IDs, correlation IDs) and `ContextBag` behavior (thread safety, conflict detection).
  - Provide code samples showing service extraction via `extract_service()` and emitting events via `try_emit_event()`.

### 4.2 Pipeline Composition & Subpipelines
* **Docs to touch:** `docs/api/pipeline.md`, `docs/advanced/subpipelines.md`, `docs/api/events.md`, `docs/advanced/composition.md`.
* **Key actions:**
  - Rewrite PipelineBuilder chapter with fluent API, cycle detection, and `PipelineSpec.inputs/outputs` examples.
  - Introduce `UnifiedStageGraph` vs legacy `StageGraph`, call out `UnifiedPipelineCancelled` / `UnifiedStageExecutionError`.
  - Add subpipeline orchestration guide covering `SubpipelineSpawner`, `ChildRunTracker`, and event lifecycle (spawned/completed/failed/canceled) with payload schemas and monitoring tips.

### 4.3 Tools, Projector, and Utilities
* **Docs to touch:** `docs/guides/tools.md`, `docs/api/tools.md`, new `advanced/projector.md`, `docs/api/utils.md` (or appendix).
* **Key actions:**
  - Align AdvancedToolExecutor docs with v2 implementation: constructor signature, internal registry, undo store, approval service wiring, event emission.
  - Document tool adapters (`DictContextAdapter`, `adapt_context`) and approval events (`ApprovalRequestedEvent`, `ApprovalDecidedEvent`).
  - Publish WebSocket projector API/guide with diagrams, message schema, and `test_app` reference implementation.
  - Describe `FrozenDict`/`FrozenList` semantics and how child pipelines rely on immutability for isolation.

### 4.4 Protocols, Extensions, and Integration
* **Docs to touch:** new `docs/api/protocols.md`, `docs/advanced/extensions.md`, new `guides/runtime-integration.md`, `docs/guides/authentication.md`, `docs/guides/observability.md`.
* **Key actions:**
  - Provide per-protocol responsibilities, lifecycle hooks, and minimal implementations for `RunStore`, `ConfigProvider`, `ExecutionContext`, `CorrelationIds`.
  - Clarify extension registry usage (registering typed extensions, retrieving helpers, stability expectations).
  - Create runtime integration guide showing FastAPI/worker embedding, cancellation propagation, and config injection patterns.
  - Expand auth/interceptor guide with organization enforcement and token validation walkthroughs; fix `InterceptorContext` references to the exported type.

### 4.5 Testing, Recovery, and Cross-links
* **Docs to touch:** new `docs/advanced/testing.md`, `docs/advanced/errors.md`, `docs/index.md`, `README.md`.
* **Key actions:**
  - Author testing playbook leveraging `ContextSnapshot`, serializable fixtures, and `tests/benchmarks`.
  - Document recovery flows (RetryableStage, circuit breaker, timeout interceptors, manual retries).
  - Add a root API index mapping `stageflow.<symbol>` to authoritative doc sections and ensure cross-links/“See also” blocks connect related guides (e.g., StagePorts ↔ Context ↔ Pipeline).
  - Fix all broken relative links, especially under `advanced/subpipelines.md` and `guides/interceptors.md`.

---

## 5. Acceptance Criteria & Metrics

1. **Parity Checklist:** Every symbol exported from `stageflow/__init__.py`, `stageflow/pipeline/__init__.py`, and `stageflow/context/__init__.py` is referenced in at least one doc page or appendix.
2. **Guide Coverage:** New guides exist for StagePorts, StageInputs, ContextBag, subpipelines, projector, correlation IDs, runtime integration, and testing.
3. **Accuracy:** `docs/api/context.md`, `docs/api/pipeline.md`, and `docs/api/tools.md` reflect current constructor signatures, fields, and behaviors—as validated via code snippets linked to tests.
4. **Observability:** Subpipeline lifecycle events and event sink configuration are documented with payload schemas and usage instructions.
5. **Navigation:** Root API index published; all previously broken intra-doc links repaired; each priority module links to relevant examples/tests.
6. **Verification:** Add a CI doc lint checklist (or manual QA checklist) ensuring any future API export changes require doc updates before release.

---

## 6. Next Actions

1. **Assign Owners:** Confirm maintainers for each workstream (pipeline, context, tools, projector, docs infra).
2. **Sequence Sprints:** Target two sprints—`SPR-006A` (parity + pipeline/context) and `SPR-006B` (tools/projector/protocols + guides)—with explicit deliverables from backlog table.
3. **Create Doc Templates:** Standardize API page layout (overview, surface, examples, cross-links) to accelerate additions.
4. **Instrument Tracking:** Record remediation progress in `STF-SPRINT-TRACKER.md` and ensure pull requests reference this plan for accountability.

---

## 7. Documentation Audit Tracker

To ensure that every exported module in `stageflow/` is mirrored by an authoritative reference in `docs/`, the audit tracker below overlays the repository the way crime-scene forensics overlay a grid on a room. Each “cell” calls out the code files, the documentation surface that should describe them, and the current coverage status so owners can mark cells complete.

### 7.1 Coverage Grid (Stageflow Modules × Documentation Surfaces)

| Module Cluster | Stageflow Files | Getting Started | Guides | API | Advanced | Examples | Status / Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Root API & Core Types | `stageflow/__init__.py`, `core/stage_*`, `stages/result.py` | `getting-started/concepts.md` (✅ core intro)<br>`getting-started/quickstart.md` (✅ usage) | `guides/stages.md` (⚠️ missing StageResult vs StageOutput) | `api/core.md` (⚠️ missing try_emit_event) | `advanced/errors.md` (✅ error taxonomy) | `examples/simple.md` | ⚠️ Update root export table + StageContext methods. |
| Stage Runtime Helpers (StageInputs/StagePorts) | `stages/inputs.py`, `stages/ports.py`, `stages/context.py` | — | `guides/stages.md`, `guides/context.md` (⚠️ brief mentions) | _(planned)_ `api/stages.md` (⛔ missing) | `advanced/composition.md` (⚠️ indirect) | `examples/transform-chain.md` | ⛔ Create dedicated API + guide coverage. |
| Context System & Bags | `context/bag.py`, `context/context_snapshot.py`, `context/types.py` | `getting-started/concepts.md` (⚠️ high-level) | `guides/context.md` (⚠️ outdated fields) | `api/context.md` (⛔ missing configuration/service/parent IDs) | `advanced/testing.md` (⚠️ limited) | `examples/full.md` (fork usage) | 🔴 Highest priority parity work. |
| Pipeline Assembly & DAG Validation | `pipeline/builder.py`, `pipeline/spec.py`, `pipeline/dag.py`, `pipeline/pipeline.py` | `getting-started/quickstart.md` (⚠️ legacy builder) | `guides/pipelines.md` (⚠️ no DAG validation) | `api/pipeline.md` (⛔ stale) | `advanced/composition.md` (⚠️ partial) | `examples/parallel.md`, `examples/full.md` | 🔴 Rewrite docs for PipelineBuilder + UnifiedStageGraph. |
| Subpipelines & Child Tracking | `pipeline/subpipeline.py`, `pipeline/interfaces.py` (child events) | — | `guides/pipelines.md` (⚠️ only mentions) | `api/events.md` (⛔ no child events) | `advanced/subpipelines.md` (⚠️ missing tracker APIs) | `examples/full.md` (child runs) | 🔴 Document spawner/tracker APIs + events. |
| Tools Execution & Approvals | `tools/executor_v2.py`, `tools/adapters.py`, `tools/approval.py`, `tools/tool.py` | `getting-started/quickstart.md` (⚠️ v1 syntax) | `guides/tools.md` (⚠️ outdated config) | `api/tools.md` (⛔ mismatch) | `advanced/custom-interceptors.md` (indirect) | `examples/agent-tools.md`, `examples/chat.md` | 🔴 Refresh docs for v2 executor, adapters, approvals. |
| Auth & Interceptors | `auth/interceptors.py`, `auth/context.py`, `pipeline/interceptors.py` | `getting-started/concepts.md` (auth mention) | `guides/authentication.md`, `guides/interceptors.md` (⚠️ references wrong InterceptorContext) | `api/auth.md`, `api/interceptors.md` (⚠️ shallow) | `advanced/custom-interceptors.md` | `examples/full.md` (auth) | 🟠 Expand interceptor context + auth tenancy docstrings. |
| Observability & Event Sinks | `events/sink.py`, `observability/__init__.py`, `core/stage_context.py (try_emit_event)` | — | `guides/observability.md` (⚠️ missing sink config) | `api/events.md`, `api/observability.md` (⚠️ outdated) | `advanced/errors.md` | `examples/full.md` (logging) | 🟠 Add sink configuration + correlation IDs guidance. |
| Projector / Real-time | `projector/service.py`, `projector/__init__.py` | — | `guides/tools.md` (❌) | — | — | `examples/agent-tools.md` (WS updates) | ⛔ Publish `advanced/projector.md` + API snippet. |
| Protocols & Extensions | `protocols.py`, `extensions.py` | `getting-started/concepts.md` (mentions) | `guides/observability.md`, `guides/authentication.md` (⚠️ partial) | _(planned)_ `api/protocols.md` (⛔) | `advanced/extensions.md` (⚠️ lacks TypedExtension examples) | — | 🟠 Create protocol reference + integration guide. |
| Utilities & ContextBag / Frozen types | `utils/frozen.py`, `context/bag.py`, `context/enrichments.py` | — | `guides/context.md` (⚠️ surface only) | `api/context.md` (⛔) | `advanced/testing.md` (⚠️) | `examples/full.md` (implicit) | 🟡 Add appendix on immutability + bag conflict handling. |
| Agent Surface | `agent/__init__.py` (re-exports) | — | — | — | — | `examples/agent-tools.md` (⚠️ only place) | 🟡 Decide whether to deprecate or document agent entry points. |

### 7.2 Doc Sweep Checklist (per file)

Use this checklist to drive line-by-line verification. Each entry names the file, the Stageflow modules it must mirror, and the current state so owners can mark cells complete.

| Doc File | Category | Stageflow Areas to Audit | Status | Notes / Actions |
| --- | --- | --- | --- | --- |
| `docs/index.md` | Index | Root exports overview | ⚠️ | Add table mapping `stageflow.<symbol>` → doc page. |
| `getting-started/installation.md` | Getting Started | Packaging / pyproject | ✅ | Up to date—verify pip workflow when version bumps. |
| `getting-started/concepts.md` | Getting Started | Core, Pipeline, Context overview | ⚠️ | Update StageContext vs PipelineContext diagrams. |
| `getting-started/quickstart.md` | Getting Started | Pipeline builder basics, Stage signature | ⚠️ | Replace `run(ctx)` examples with `execute(ctx)` + PipelineBuilder. |
| `guides/stages.md` | Guide | Stage protocol, StageInputs/Ports | ⛔ | Add runtime helper section + StageResult vs StageOutput. |
| `guides/context.md` | Guide | PipelineContext, ContextBag, StageContext | 🔴 | Include configuration/service fields, parent IDs, fork/is_child_run. |
| `guides/pipelines.md` | Guide | PipelineBuilder, registry, composition | 🔴 | Rewrite around new builder, DAG validation, inputs/outputs. |
| `guides/tools.md` | Guide | Tool registry, AdvancedToolExecutor v2 | 🔴 | Update constructor signature, adapters, approval flow. |
| `guides/interceptors.md` | Guide | Interceptor pipeline, context object | ⚠️ | Fix InterceptorContext import path, add advanced examples. |
| `guides/observability.md` | Guide | Event sinks, loggers, correlation IDs | ⚠️ | Document set_event_sink, correlation propagation. |
| `guides/authentication.md` | Guide | Auth interceptors, tenancy | ⚠️ | Add org enforcement flow from `auth/interceptors.py`. |
| `guides/stages.md` | Guide | Stage runtime | ⚠️ | (Duplicate entry consolidated above—track once). |
| `guides/context.md` | Guide | Context | ⚠️ | (Duplicate entry consolidated above—track once). |
| `docs/guides/stages.md` | Guide | Stage runtime | ⚠️ | (Ensure deduped). |
| `docs/guides/context.md` | Guide | Context | ⚠️ | (Ensure deduped). |
| `api/core.md` | API | Stage protocol, StageOutput, StageContext | ⚠️ | Add try_emit_event, timer updates. |
| `api/context.md` | API | PipelineContext, ContextBag, snapshot | 🔴 | Align constructor signatures + examples. |
| `api/pipeline.md` | API | PipelineBuilder, specs, DAG | 🔴 | Document builder API, UnifiedStageGraph, validation errors. |
| `api/tools.md` | API | Tool executor, adapters, events | 🔴 | Sync with executor_v2, approval events, undo store. |
| `api/auth.md` | API | Auth interceptors, events | ⚠️ | Expand on organization enforcement + token ctx. |
| `api/interceptors.md` | API | Interceptor interfaces | ⚠️ | Include new pipeline interfaces (Retryable/Conditional). |
| `api/events.md` | API | Event sinks + pipeline/subpipeline events | ⛔ | Add child pipeline events + try_emit_event usage. |
| `api/observability.md` | API | Observability helpers, loggers | ⚠️ | Document NoOpPipelineRunLogger exports. |
| `advanced/composition.md` | Advanced | Complex DAG layouts | ⚠️ | Reference new builder + StageInputs dataflow. |
| `advanced/subpipelines.md` | Advanced | Subpipeline orchestration | 🔴 | Add tracker APIs, events, cancellation cascade. |
| `advanced/testing.md` | Advanced | Benchmarks, ContextSnapshot replay | ⚠️ | Incorporate latest tests + ContextBag usage. |
| `advanced/custom-interceptors.md` | Advanced | Custom interceptor authoring | ⚠️ | Mention new interfaces & auth links. |
| `advanced/errors.md` | Advanced | Error taxonomy | ✅ | Cross-link to pipeline & core API (minor updates). |
| `advanced/extensions.md` | Advanced | ExtensionRegistry, TypedExtension | ⚠️ | Add usage scenarios + protocol tie-ins. |
| `examples/simple.md` | Example | Core pipeline | ✅ | Verify StageContext signature. |
| `examples/parallel.md` | Example | Parallel execution | ⚠️ | Add note about builder APIs + StageInputs. |
| `examples/full.md` | Example | End-to-end orchestration | ⚠️ | Highlight context forking + child runs. |
| `examples/agent-tools.md` | Example | Agent tooling + projector | 🔴 | Reference projector doc once created. |
| `examples/chat.md` | Example | Tool executor | ⚠️ | Align with executor_v2 usage. |
| `examples/transform-chain.md` | Example | Stage chaining | ⚠️ | Document StageInputs immutability. |
| `docs/index.md` | Index | Navigation hub | ⚠️ | Add links to new API/guide pages once published. |

_Note: Duplicate rows are intentional reminders to mark both guide + API updates where files overlap (e.g., context/stages). Merge tracking in sprint tracker when work begins._

---

## 8. Remediation Progress (Jan 9, 2026)

### Completed Updates

| File | Changes Made |
|------|-------------|
| `docs/api/context.md` | Added `StageInputs` and `StagePorts` API documentation with full method signatures, attributes, and factory functions |
| `docs/api/events.md` | Added subpipeline events section (`pipeline.spawned_child`, `pipeline.child_completed`, `pipeline.child_failed`, `pipeline.canceled`) |
| `docs/api/protocols.md` | **NEW FILE** - Created comprehensive protocol reference for `ExecutionContext`, `EventSink`, `RunStore`, `ConfigProvider`, `CorrelationIds` |
| `docs/api/pipeline.md` | Added `PipelineBuilder` API, `CycleDetectedError`, `PipelineValidationError` documentation |
| `docs/index.md` | Added Root Exports Index mapping all `stageflow.*` symbols to documentation pages; added link to new protocols.md |
| `docs/advanced/subpipelines.md` | Added `SubpipelineSpawner` API with `max_depth`, `ChildRunTracker` API, `SubpipelineResult`, `MaxDepthExceededError`, and full event payload schemas |
| `docs/advanced/testing.md` | Added testing utilities section: `create_test_snapshot`, `create_test_stage_context`, `create_test_pipeline_context`, snapshot validation |
| `docs/guides/context.md` | Updated "Accessing Upstream Outputs" section to document `StageInputs` pattern with methods |
| `docs/guides/stages.md` | Added "From Upstream Stages (StageInputs)" and "Injected Services (StagePorts)" sections |

### Remaining Items (Lower Priority)

1. **Tools v2 refresh** - `docs/api/tools.md` and `docs/guides/tools.md` could use executor v2 constructor details
2. **Auth interceptors** - `docs/guides/authentication.md` is comprehensive but could add more examples

---

## 9. System/Code Gaps - RESOLVED

All identified system-level gaps have been addressed:

### 9.1 Missing Exports - ✅ RESOLVED

| Symbol | Resolution |
|--------|------------|
| `StageInputs`, `StagePorts` | Now exported from `stageflow/__init__.py` and `stageflow.stages` |
| `CorePorts`, `LLMPorts`, `AudioPorts` | New modular ports exported from root and stages module |
| `SubpipelineSpawner`, `ChildRunTracker` | Now exported from `stageflow/__init__.py` and `stageflow.pipeline` |
| `CycleDetectedError`, `MaxDepthExceededError` | Now exported from `stageflow/__init__.py` |
| `create_stage_inputs`, `create_stage_ports` | Now exported from root |

### 9.2 API Inconsistencies - ✅ RESOLVED

| Issue | Resolution |
|-------|------------|
| `inputs` access pattern | Added `StageContext.inputs` property for type-safe access |
| `StageContext.emit_event` correlation | Events now enriched with `pipeline_run_id`, `request_id`, `execution_mode` |

**StagePorts Refactoring - ✅ RESOLVED (COMPLETE)**

The `StagePorts` field explosion has been fully addressed by splitting into modular ports:

- **CorePorts** - Essential capabilities (db, status, logging)
- **LLMPorts** - Language model capabilities (provider, streaming)
- **AudioPorts** - Audio processing capabilities (TTS/STT, streaming)
- **Legacy StagePorts** - Completely removed (no backward compatibility)

This follows the Interface Segregation Principle and makes the API much cleaner.

**Implementation:**
- Created modular port classes with focused responsibilities
- Added factory functions for each port type
- Updated exports in `stageflow/__init__.py` and `stageflow.stages/__init__.py`
- Updated documentation to show modular usage patterns
- Completely removed legacy `StagePorts` and all deprecated factory functions
- Updated all tests to use new modular ports
- Fixed all import references throughout the codebase

### 9.3 Missing Validation/Safety - ✅ RESOLVED

| Gap | Resolution |
|-----|------------|
| No cycle detection error type | Created `CycleDetectedError` with `cycle_path` attribute showing exact cycle |
| `SubpipelineSpawner` no depth limit | Added `max_depth` parameter (default: 5) and `MaxDepthExceededError` |

**Remaining (acceptable risk):**
- `ContextBag.write` async - kept as-is; async is correct for thread-safety

### 9.4 Observability Gaps - ✅ RESOLVED

| Gap | Resolution |
|-----|------------|
| No correlation ID in `StageContext.emit_event` | Events now include `pipeline_run_id`, `request_id`, `execution_mode` |
| No event for stage skip | Added `stage.{name}.skipped` event emission in `UnifiedStageGraph` |

**Remaining (future work):**
- None - `ChildRunTracker` metrics have been implemented

### 9.5 Testing Infrastructure - ✅ RESOLVED

Created `stageflow/testing.py` with:

| Function | Purpose |
|----------|----------|
| `create_test_snapshot()` | Create `ContextSnapshot` with sensible defaults |
| `create_test_stage_context()` | Create `StageContext` for testing stages |
| `create_test_pipeline_context()` | Create `PipelineContext` for testing interceptors |
| `validate_snapshot()` | Validate snapshot with detailed error reporting |
| `validate_snapshot_strict()` | Validate and raise on invalid |
| `snapshot_from_dict_strict()` | Create from dict with validation |

### 9.6 Documentation-Code Sync - Deferred

| Issue | Status |
|-------|--------|
| No docstring enforcement | Future CI enhancement |
| No example validation | Future CI enhancement |
| Version not in docs | Future enhancement |
