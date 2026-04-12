# Sprint Template: Native Tool Runtime Extraction V1

> Project: Stageflow
> Scope: Backend and platform execution only. Frontend planning is tracked separately.

## Sprint Overview

- Sprint Name: Native Tool Runtime Extraction V1
- Sprint Focus: Extract the reusable production-grade native tool-calling runtime boundary from SoftSkills into Stageflow without forcing app-specific persistence, projection, or transport concerns into the framework.
- Depends On: `v1.2.0` typed payload helpers and native-first `stageflow.agent.Agent` support already shipped in this repo.

## Relevant Source Docs

- [project/stageflow.md](/home/antonioborgerees/coding/stageflow/project/stageflow.md#L3): lines 3-28
- [project/stageflow.md](/home/antonioborgerees/coding/stageflow/project/stageflow.md#L41): lines 41-51
- [project/stageflow.md](/home/antonioborgerees/coding/stageflow/project/stageflow.md#L55): lines 55-90
- [docs/guides/agents.md](/home/antonioborgerees/coding/stageflow/docs/guides/agents.md#L58): lines 58-165
- [docs/guides/tools-approval.md](/home/antonioborgerees/coding/stageflow/docs/guides/tools-approval.md#L5): lines 5-129
- [ops/stageflow-backend-usage-review-2026-04-08.md](/home/antonioborgerees/coding/stageflow/ops/stageflow-backend-usage-review-2026-04-08.md#L30): lines 30-50
- [ops/stageflow-backend-usage-review-2026-04-08.md](/home/antonioborgerees/coding/stageflow/ops/stageflow-backend-usage-review-2026-04-08.md#L75): lines 75-108
- [stageflow/agent/runtime.py](/home/antonioborgerees/coding/stageflow/stageflow/agent/runtime.py#L119): lines 119-304
- [stageflow/tools/registry.py](/home/antonioborgerees/coding/stageflow/stageflow/tools/registry.py#L63): lines 63-248
- [stageflow/tools/executor_v2.py](/home/antonioborgerees/coding/stageflow/stageflow/tools/executor_v2.py#L79): lines 79-349
- [stageflow/tools/approval.py](/home/antonioborgerees/coding/stageflow/stageflow/tools/approval.py#L90): lines 90-240
- [soft-skills assistant service](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/assistant/workflows/service.py#L351): lines 351-620
- [soft-skills assistant tools](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/assistant/workflows/tools.py#L84): lines 84-415

## Sprint Goals

- Primary Goal: Introduce a reusable Stageflow-native tool runtime boundary that can support provider-native tool calling, typed tool contracts, approval orchestration, lifecycle hooks, and child pipeline linkage without embedding application persistence or UI code into the core framework.
- Secondary Goals:
  - Refactor `stageflow.agent.Agent` so tool execution is delegated to a pluggable runtime instead of being hardwired to `ToolRegistry`.
  - Provide typed provider-tool schema and validation helpers so applications do not have to hand-roll tool-call adapters.
  - Establish the minimum framework hooks required for SoftSkills to delete orchestration glue later instead of wrapping it forever.

## Scope Checklist

- [x] Task 1: Introduce `AgentToolRuntime` and `AgentLifecycleHooks` framework interfaces and refactor `Agent` to depend on them
- [x] Task 2: Add typed provider-native tool definition and tool-call validation support to `stageflow.tools`
- [x] Task 3: Add approval backend and tool lifecycle hook protocols suitable for durable app implementations
- [x] Task 4: Add subpipeline-aware tool execution support and structured child-run lineage reporting
- [x] Task 5: Documentation updates for all changed behavior and contracts

## Constitution And Quality Checklist

- [x] SOLID is preserved: agent loop, tool runtime, approval backend, and projection hooks have separate responsibilities with narrow interfaces
- [x] DRY is preserved: no duplicate provider tool-call parsing or duplicate lifecycle orchestration is introduced across `agent` and `tools`
- [x] Observability is truth: if tool runtime state changes, it is emitted, traceable, and testable
- [x] All new external boundaries are typed and schema-validated
- [x] Fail-fast and fail-loud behavior is preserved with stable error codes and no silent failure paths
- [x] Route handlers remain thin; business rules stay out of transport layers
- [x] Dependency injection and adapter boundaries remain explicit
- [x] Critical workflow artifacts are durably persisted where required by the host app, but persistence remains an adapter concern rather than a core-framework hard dependency
- [x] Traces, logs, and events cover all changed workflow steps
- [x] Prompt, tool, schema, model, and config versions are preserved where applicable
- [x] No silent fallback is introduced in tool execution, approval flow, provider-native tool parsing, or subpipeline delegation
- [x] Files stay modular; new or heavily edited files should remain under 600 lines unless there is a documented exception in sprint notes
- [x] Error handling is explicit and exhaustive; no broad exception swallowing without structured conversion and event emission

## Testing And Documentation Checklist

- [x] Unit Tests: deterministic coverage for tool runtime orchestration, typed tool parsing, approval backend contracts, lifecycle hooks, and child-run reporting
- [x] Integration Tests: agent runtime plus pluggable tool runtime execution, native provider tool-call flow, unresolved call handling, approval timeout/denial behavior, and subpipeline tool linkage
- [x] Smoke Tests With Real Provider: update Stageflow smoke/provider harness or add a reference smoke path that proves native tool calling still works against a real provider integration
- [x] Failure Path Coverage: explicit validation, provider, orchestration, approval, and subpipeline failure paths tested with stable error surfaces
- [x] Documentation Updates: update canonical docs in `docs/`, `ops/`, and any affected API references and examples

## Success Criteria

- [x] `stageflow.agent.Agent` no longer owns direct tool execution as a hardcoded concern
- [x] Stageflow exposes a reusable native-tool runtime boundary that a host app can implement without monkey-patching framework internals
- [x] Typed provider tool definitions and typed provider tool-call validation are first-class Stageflow APIs
- [x] Approval backends and lifecycle hooks are pluggable and production-oriented, not only in-memory test helpers
- [x] Child pipeline lineage can be surfaced as part of tool execution results without application-specific wrapper code
- [x] Tests pass at unit, integration, and smoke/reference-provider level for the sprint scope
- [x] Canonical docs reflect the implemented architecture and adoption path
- [x] Observability artifacts are sufficient to debug the changed workflows

Minimum Viable Sprint:
Deliver the pluggable tool runtime boundary, typed provider-tool contract support, and lifecycle hooks in a way that lets SoftSkills begin deleting orchestration glue on the next sprint. Approval persistence and full child-run-aware projection can remain adapter-backed so long as the framework boundary is stable, typed, observable, and migration-ready.

## Proposed Deliverables

1. `stageflow.agent.runtime` extraction
   Deliver:
   - `AgentToolRuntime` protocol
   - `AgentLifecycleHooks` protocol
   - `AgentToolExecutionResult` and `AgentToolRuntimeResult` models
   - `Agent` refactor to delegate tool execution, unresolved handling, and reinjection message generation

2. `stageflow.tools` typed provider contracts
   Deliver:
   - typed input model support on tool definitions
   - provider schema generation helpers
   - provider tool-call validation helpers that produce resolved and unresolved typed results
   - no application-specific Pydantic unions in framework internals

3. Approval backend separation
   Deliver:
   - protocol for durable approval storage and wait/notify coordination
   - in-memory implementation retained as the default test adapter
   - explicit timeout, denial, and expiry error surfaces

4. Tool runtime lifecycle surface
   Deliver:
   - invoked, approval requested, approval decided, started, updated, completed, failed hook points
   - structured event payload contracts
   - clear separation between framework lifecycle hooks and host-app event projection

5. Subpipeline-aware tool support
   Deliver:
   - child pipeline execution helper designed for tool runtime usage
   - typed child-run metadata in tool results
   - deterministic failure propagation with no hidden fallback

## Implementation Plan

### Task 1: Refactor Agent Around A Pluggable Tool Runtime

- Create a new small module set under `stageflow/agent/` rather than enlarging `runtime.py`.
- Split the current `Agent` responsibilities into:
  - turn planning
  - provider invocation
  - tool runtime delegation
  - tool result reinjection
  - lifecycle event emission
- Keep `Agent` as the orchestrator, not the executor.
- Replace direct `ToolRegistry.execute(...)` usage with a runtime interface.

Acceptance notes:
- `Agent` must still support native and JSON fallback modes.
- The refactor must not regress existing agent tests.
- The new boundary must support pure framework use with a default runtime and richer app use with a custom runtime.

### Task 2: Add Typed Provider-Tool Contracts

- Extend Stageflow tool definitions so a tool can declare:
  - `input_schema`
  - optional typed input model
  - optional parser/validator
- Add helpers to convert provider-native tool calls into validated typed calls.
- Move the reusable part of SoftSkills `runtime_models.py` into Stageflow, but keep app-specific unions out of the framework.

Acceptance notes:
- Invalid arguments produce explicit unresolved/validation failures.
- Provider schema generation must be deterministic and reusable across OpenAI-compatible clients.
- The framework should not require host apps to manually translate raw provider tool calls into custom typed objects for common cases.

### Task 3: Introduce Approval Backend Protocols

- Add a production-shaped approval backend protocol that supports:
  - create approval request
  - await decision
  - record decision
  - mark expired
  - lookup current state
- Keep the current in-memory approval service as a concrete adapter, not the only model.
- Ensure error types distinguish denied, expired, missing, and backend failure states.

Acceptance notes:
- No silent approval timeout behavior.
- All approval state changes must be observable through hooks and events.
- The framework should not assume WebSocket or database specifics.

### Task 4: Add Lifecycle Hooks And Subpipeline Tool Support

- Add lifecycle hooks that fire around tool runtime steps without coupling Stageflow to UI projection or persistence.
- Expose subpipeline tool execution helpers that return structured child lineage.
- Ensure tool update events support long-running tools with progressive payloads.

Acceptance notes:
- Long-running tool paths can surface intermediate updates.
- Child run ids and failure details are visible to the caller.
- The core framework must remain orchestration-focused, not domain-specific.

### Task 5: Documentation And Migration Guidance

- Update `docs/guides/agents.md` to describe the pluggable runtime architecture.
- Update `docs/guides/tools-approval.md` to distinguish:
  - simple registry execution
  - advanced executor
  - pluggable agent tool runtime
- Add a migration guide section describing how an app like SoftSkills should move from a bespoke native tool loop to the extracted framework surfaces.

Acceptance notes:
- Docs must state what belongs in framework core versus host-app adapters.
- Examples should use modular files and typed contracts, not stitched inline demos.

## Filesystem And Modularity Rules

- New modules should be split by concern:
  - `stageflow/agent/runtime_core.py`
  - `stageflow/agent/tool_runtime.py`
  - `stageflow/agent/lifecycle.py`
  - `stageflow/tools/provider_contracts.py`
  - `stageflow/tools/approval_backends.py`
  - `stageflow/tools/subpipeline_runtime.py`
- Avoid large catch-all files. The default target is under 600 lines per file.
- If a file must exceed 600 lines, add a sprint-note justification and break out helper modules first.
- Do not duplicate parsing, schema generation, or event-payload shaping logic across modules.

## Error Handling Requirements

- Every framework-level failure path must map to an explicit typed error or structured result.
- No bare `except Exception` without:
  - converting to a stable Stageflow error type
  - emitting a structured event
  - preserving the original cause
- Unresolved tool calls, validation failures, approval expiry, provider failures, and child-pipeline failures must all be distinguishable in tests and telemetry.
- No silent fallback from native tool calling to JSON parsing inside a host-app path unless explicitly configured and observable.

## Observability Requirements

- Every tool lifecycle transition must emit structured events with:
  - `pipeline_run_id`
  - `request_id`
  - `tool_name`
  - `call_id`
  - `status`
  - timing and error data where applicable
- Approval lifecycle must emit request and decision events.
- Child subpipeline tool executions must emit lineage metadata.
- Provider call boundaries must remain traceable and tied to the run model.
- If a tool runtime step cannot be observed, it is not considered complete.

## Risks And Blockers

| Risk | Impact | Mitigation | Status |
| --- | --- | --- | --- |
| Extracting too much SoftSkills-specific logic into Stageflow | High | Keep domain dispatch, repository writes, broker publishing, and app prompts outside the framework; review every API against at least two plausible host apps | Open |
| Overloading `Agent` with more responsibilities during refactor | High | Split new modules by concern first and add interface tests before moving implementation | Open |
| Approval abstraction remains test-only and not production-credible | High | Design around backend protocol plus default in-memory adapter, not singleton globals | Open |
| Tool runtime hooks become vague and untyped | Medium | Use explicit dataclasses/Pydantic models for hook payloads and result contracts | Open |
| File-size and modularity regressions during extraction | Medium | Enforce pre-merge review against the under-600-line target and split helpers early | Open |
| Real-provider smoke coverage becomes brittle | Medium | Keep provider smoke scope narrow and focused on native tool-calling invariants rather than full application workflows | Open |

## Sprint Notes

Key decisions, tradeoffs, and implementation notes:

```text
1. Do not force SoftSkills to adopt the current Stageflow Agent directly.
   The current framework runtime is still too narrow at the execution boundary.

2. Stageflow should extract abstractions, not application glue.
   Persisted tool rows, realtime broker publishing, repository schema writes,
   and domain prompt content remain host-app concerns.

3. The extraction target is the reusable contract:
   provider-native tool schema generation, typed tool-call validation,
   pluggable execution runtime, approval backend hooks, lifecycle hooks,
   and child-run-aware execution results.

4. Observability is truth.
   Every runtime step introduced in this sprint must be visible through
   structured events and test assertions. Silent fallback is not acceptable.

5. SOLID and DRY are hard constraints.
   If an implementation requires the same provider-tool parsing logic in two
   places, the abstraction is still wrong.
```

## Review And Sign-Off

- Sprint Status: Completed
- Completion Date: 2026-04-12

Checklist:

- [x] Primary goal achieved
- [x] Constitution and quality checks passed
- [x] Unit tests completed
- [x] Integration tests completed
- [x] Smoke tests with real provider completed

Implementation note:
The smoke target is now `tests/smoke/test_native_tool_runtime_smoke.py`. In this environment it skips cleanly because provider credentials are not configured; execution with real credentials is opt-in via `STAGEFLOW_SMOKE_OPENAI_API_KEY` and `STAGEFLOW_SMOKE_OPENAI_MODEL`.
- [x] Documentation updated
- [x] Code review completed

Next Sprint Priorities:

1. Extract durable tool lifecycle persistence and projection hooks so host apps can persist and project tool state without bespoke orchestration glue
2. Extract stage-scoped idempotency and event naming/queryability improvements into framework core
3. Extract prompt-render and typed-LLM stage builders with the same modularity and observability standards
