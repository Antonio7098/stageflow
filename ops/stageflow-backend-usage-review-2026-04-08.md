# Stageflow Backend Usage Review

> Project: SoftSkills
> Report Type: Backend architecture review and framework feedback
> Output Location: `ops/reports/stageflow-backend-usage-review-2026-04-08.md`
> Scope: Backend Stageflow usage across orchestration, generation, assistant, and admin-agent flows
> Review Date: 2026-04-08
> Author: Assistant

## Review Inputs

- [ops/process/stageflow-reporting.md](/home/antonioborgerees/df/soft-skills/ops/process/stageflow-reporting.md)
- [ops/mvp-spec/foundational/stageflow-guide.md](/home/antonioborgerees/df/soft-skills/ops/mvp-spec/foundational/stageflow-guide.md)
- [backend/src/soft_skills_backend/platform/workflows/stageflow.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/platform/workflows/stageflow.py)
- [backend/src/soft_skills_backend/platform/workflows/stageflow_runtime.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/platform/workflows/stageflow_runtime.py)
- [backend/src/soft_skills_backend/modules/practice/use_cases/practice_service.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/practice/use_cases/practice_service.py)
- [backend/src/soft_skills_backend/modules/progression/workflows/service.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/progression/workflows/service.py)
- [backend/src/soft_skills_backend/modules/evaluation/workflows/service.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/evaluation/workflows/service.py)
- [backend/src/soft_skills_backend/modules/catalog/workflows/generation/collection_pipeline.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/catalog/workflows/generation/collection_pipeline.py)
- [backend/src/soft_skills_backend/modules/catalog/workflows/generation/prompt_item_pipeline.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/catalog/workflows/generation/prompt_item_pipeline.py)
- [backend/src/soft_skills_backend/modules/catalog/workflows/generation/workers.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/catalog/workflows/generation/workers.py)
- [backend/src/soft_skills_backend/modules/assistant/workflows/service.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/assistant/workflows/service.py)
- [backend/src/soft_skills_backend/modules/assistant/workflows/tools.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/assistant/workflows/tools.py)
- [backend/src/soft_skills_backend/modules/admin_agent/workflows/service.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/admin_agent/workflows/service.py)
- [backend/src/soft_skills_backend/modules/admin/workflows/prompt_render_stage.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/admin/workflows/prompt_render_stage.py)
- [/home/antonioborgerees/coding/stageflow/docs/guides/agents.md](/home/antonioborgerees/coding/stageflow/docs/guides/agents.md)
- [/home/antonioborgerees/coding/stageflow/docs/guides/tools.md](/home/antonioborgerees/coding/stageflow/docs/guides/tools.md)
- [/home/antonioborgerees/coding/stageflow/docs/examples/agent-tools.md](/home/antonioborgerees/coding/stageflow/docs/examples/agent-tools.md)

## Executive Summary

Stageflow was a strong fit for SoftSkills where the problem was explicit orchestration: DAG structure, parallel enrichments, typed stage boundaries, child workflow isolation, and traceable run execution. Practice, progression, evaluation, and most catalog flows benefited directly from that model.

The weak point was the agent/tooling story. In the codebase, the real production agent implementation does not use Stageflow's `Agent`, `AgentStage`, `ToolRegistry`, or `AdvancedToolExecutor`. It uses Stageflow for the outer DAG, but the actual assistant loop is a custom provider-native tool-calling runtime built around `complete_with_tools(...)`, typed tool contracts, persisted approvals, realtime stream events, subpipeline delegation, and cancellation propagation. That is the clearest sign that the current Stageflow agent abstraction is not at the right boundary for production use.

The most reusable abstractions SoftSkills had to build locally were:

- logged pipeline and subpipeline execution with correlation and observability
- stage-scoped idempotency
- prompt render stages
- typed stage-result helpers
- cooperative cancellation checkpoints
- ordered event emission for UI-facing workflows
- a provider-native tool runtime with persistence and approval hooks

The framework improvement priority was clear:

1. Keep Stageflow opinionated about orchestration.
2. Move the repeated operational scaffolding into first-class framework helpers.
3. Replace the current agent-centered JSON loop with a native tool-calling agent runtime.

## Implementation Update (2026-04-09)

This repository now implements a focused subset of the improvements identified in
this review.

### Shipped in Stageflow

- Typed stage payload helpers now exist as first-class framework APIs:
  `StagePayloadResult`, `ok_output(...)`, `cancel_output(...)`,
  `fail_output(...)`, `payload_from_inputs(...)`,
  `payload_from_results(...)`, and `summary_from_output(...)`.
- Cooperative cancellation now has explicit runtime helpers:
  `ctx.raise_if_cancelled()` and `await ctx.cancellation_checkpoint()`
  on both `PipelineContext` and `StageContext`.
- The unified runtime now supports before-stage-start hooks for
  observability and progress publication through
  `PipelineContext.add_before_stage_start_hook(...)`.
- Child pipeline execution now supports explicit parent `ctx.data`
  inheritance rules through `PipelineContext.fork(..., inherit_data=..., data_overrides=...)`
  and matching `SubpipelineSpawner.spawn(...)` parameters.
- Callable stage typing has been widened so plain async stage runners no
  longer require repeated cast-based workarounds.

### Not Shipped Yet

- First-class logged pipeline/subpipeline execution with run-log hooks in the framework core.
- Prompt-render and typed-LLM stage builders.
- Richer persistence-aware tool runtime hooks for durable app-owned persistence.
- Ordered UI projection support at the framework level.

### Practical Effect

The framework now absorbs most of the "typed stage ergonomics" and a meaningful
part of the "long-running workflow ergonomics" that SoftSkills previously had to
build locally. As of 2026-04-11, the framework also absorbs the reusable native
tool-calling boundary itself; the remaining gap is durable app-specific
persistence and projection around that runtime.

### SoftSkills Adoption Status (2026-04-09)

Status in this repository after the Stageflow 1.2.0 alignment work:

- `backend/pyproject.toml` now requires `stageflow-core>=1.2.0`.
- `backend/src/soft_skills_backend/platform/workflows/stageflow.py`
  now imports Stageflow's built-in typed payload helpers directly:
  `StagePayloadResult`, `ok_output(...)`, `payload_from_inputs(...)`,
  `payload_from_results(...)`, and `summary_from_output(...)`.
- `StageflowStageResult` remains as a thin compatibility alias over
  `StagePayloadResult` so existing workflow code did not need a broad
  rewrite in the same change.
- `run_logged_subpipeline(...)` now uses Stageflow's child-context data
  inheritance support via `inherit_data=True` and `data_overrides=...`
  instead of manually rehydrating private parent data on the child context.
- `run_logged_pipeline(...)` and local child run logging still remain in
  SoftSkills because first-class logged pipeline/subpipeline execution has
  not shipped in Stageflow itself yet.
- Assistant tool runtime, approval persistence, prompt-render staging, and
  UI-facing ordered projection logic also remain local.

Verification completed during this update:

- targeted unit tests passed:
  `test_assistant_runtime.py`,
  `test_generation_streaming.py`,
  `test_practice_runtime.py`,
  `test_smoke_runner.py`
- smoke registry load passed via
  `python -m soft_skills_backend.smoke --list`
- local smoke suites passed:
  `auth-flows` and `pipeline-visualization`

Verification caveat:

- the backend virtualenv still reported installed package metadata for
  `stageflow-core` as `1.1.0`, so verification used
  `PYTHONPATH=/home/antonioborgerees/coding/stageflow` to force the local
  Stageflow checkout that contains the 1.2.0 API surface
- `practice-run-lifecycle` did not complete within the validation window, so
  that suite is not marked as passed here

## Implementation Update (2026-04-11)

This repository and SoftSkills now validate the main recommendation from this
review: the reusable boundary was the native provider tool runtime, and that
boundary now exists in Stageflow and is adopted in SoftSkills where it fit
naturally.

### Shipped in Stageflow

- A native-first agent tool runtime now exists in framework core.
- `Agent` supports provider-native tool-calling as the primary path rather than
  only a local JSON envelope loop.
- Tool execution now flows through a pluggable runtime boundary instead of
  direct registry execution inside the agent loop.
- Typed provider-tool contracts now support `input_model`-driven schema
  generation and strict provider-argument validation.
- Tool runtime I/O now supports structured `tool.updated` publication and child
  subpipeline lineage from tool execution.
- Approval handling now has an explicit backend abstraction instead of only an
  in-memory service shape.
- Logged pipeline and subpipeline execution now exist as first-class framework
  helpers rather than only as SoftSkills-local wrappers.
- Parallel logged child-run coordination now exists as a first-class framework
  helper through `run_logged_subpipelines(...)`.

### SoftSkills Adoption Status (2026-04-11)

SoftSkills did not replace its entire assistant orchestration with Stageflow's
`Agent`, which would have been forced. Instead it adopted the extracted pieces
that were actually reusable:

- assistant provider tool definitions now come from Stageflow-backed typed tool
  contracts rather than local manual schema assembly
- assistant tool-update emission now uses Stageflow runtime I/O while preserving
  SoftSkills-owned persistence and broker projection
- provider-facing generation tool schemas now preserve SoftSkills' existing
  alias semantics at the contract boundary while normalizing back into
  canonical backend command models internally

SoftSkills still intentionally keeps these concerns local:

- persisted tool-call rows and approval request storage
- websocket/broker projection policy
- assistant loop policy and final streamed response path
- app-specific subpipeline result shaping

SoftSkills has also adopted the new logged execution helpers in its local
Stageflow adapter layer, so top-level and child-run orchestration no longer
need to reimplement run logging or lineage reconstruction from scratch.

The main remaining orchestration-shaped gaps are now:

- durable persistence-aware hooks around tool lifecycle state
- ordered projection and event sink support for UI-facing workflows
- reusable prompt-render and typed-LLM stage builders

### Real Verification Completed

Verification is no longer only unit-test or local-workflow level.

Stageflow verification completed in the framework repository:

- unit and integration coverage for native tool-calling runtime, typed tool
  schemas, lifecycle hooks, approval backend abstraction, and subpipeline-aware
  tool runtime behavior

SoftSkills verification completed against the local Stageflow checkout:

- assistant unit tests passed after adoption changes
- deterministic assistant smoke passed
- provider-backed assistant read smoke passed
- provider-backed assistant generation smoke passed
- provider-backed assistant multi-tool sequence smoke passed

The important real-world result is that the new strict typed tool contracts
initially exposed a live compatibility issue in SoftSkills generation tool
schemas. The provider was still emitting legacy `counts` keys such as
`quick_practice_prompt` and `interview_prompt`, while the extracted strict
schema had narrowed to backend field names. That failure was fixed at the
provider-facing contract layer and then verified with real-provider-backed
generation smoke. That is exactly the kind of extraction validation this review
was intended to drive.

## Backend Usage Inventory

| Area | How Stageflow Was Used | Fit | Notes |
| --- | --- | --- | --- |
| Practice runtime | Guard, parallel enrich, transform, persist DAGs | Strong | Cleanest example of Stageflow doing exactly the right job |
| Progression | Orchestration of snapshot + recommendation pipeline | Strong | Domain math stayed outside Stageflow, which was correct |
| Evaluation | Thin guard -> transform -> work pipeline | Strong | Stageflow added reliability and observability without distortion |
| Catalog CRUD | Small orchestration wrappers over repository work | Good | Repetitive pipeline boilerplate suggests helper opportunities |
| Catalog generation | Parent DAG + child subpipelines + typed outputs + progress streaming | Mixed-good | Strong orchestration fit, but needed substantial local runtime scaffolding |
| Assistant turn runtime | Outer DAG plus custom native tool loop and tool execution runtime | Mixed-poor for agent layer | Stageflow useful around the agent, not as the agent |
| Admin agent | Planning + guarded tool execution + response formulation | Mixed | Useful as an orchestrated planner pipeline, but not a true reusable Stageflow agent |

## What Worked Well

- The guard/enrich/transform/work split produced readable pipelines and kept business semantics out of orchestration.
- `Pipeline.from_stages(...)` with explicit dependencies mapped well to the product's real DAG structure.
- Parallel enrich and fan-in stages gave immediate value in practice, assistant, and generation flows.
- Subpipelines were the right primitive for worker isolation and child-run lineage in generation workflows.
- Wide events, run logging, and correlation metadata made Stageflow execution reviewable after the fact.
- Using Stageflow as the coordination layer kept route handlers thin and protected modular service boundaries.

## What SoftSkills Had To Build Locally

### 1. Logged runtime wrappers

SoftSkills created local wrappers for both parent and child execution in [stageflow.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/platform/workflows/stageflow.py).

- `run_logged_pipeline(...)` centralizes context creation, timeout wiring, idempotency setup, wide-event settings, and run logging.
- `run_logged_subpipeline(...)` still reconstructs child context, preserves lineage, and logs child runs.
- As of 2026-04-09 it no longer manually rehydrates parent `data`; it now uses Stageflow's built-in child data inheritance controls.

This is valuable framework behavior, not app-specific behavior.

### 2. Stage-scoped idempotency

SoftSkills needed `StageScopedIdempotencyInterceptor` because request-level idempotency keys collided across multi-stage DAGs. This should not require a local interceptor to fix.

### 3. Prompt rendering as a reusable stage

The project created [prompt_render_stage.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/admin/workflows/prompt_render_stage.py) because prompt rendering with metadata, auditability, and strict failure behavior kept recurring.

The recurring local pattern was:

- stage emits `PromptRenderRequest`
- shared transform renders from registry
- downstream LLM stage consumes typed prompt artifact

That is generic enough to deserve framework support through interfaces, even if the exact prompt registry remains application-owned.

### 4. Typed stage-result ergonomics

SoftSkills introduced `StageflowStageResult`, `ok_output(...)`, `payload_from_inputs(...)`, and `payload_from_results(...)` because raw `StageOutput` access is too loose and repetitive for typed application code.

As of 2026-04-09, the helper functions now come directly from Stageflow 1.2.0 and `StageflowStageResult` is only a compatibility alias over the framework type.

The number of repeated `StageflowStageResult(...)` wrappers across backend workflows is still a signal that the application may want a later cleanup pass to rename local compatibility types and reduce remaining wrapper noise.

### 5. Cancellation and progress scaffolding

Generation pipelines needed local cancellation windows and manual progress publication in [collection_pipeline.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/catalog/workflows/generation/collection_pipeline.py#L99).

SoftSkills had to add:

- explicit `refresh_cancellation(...)`
- local `_yield_for_cancel()` checkpoints
- manual `StageOutput.cancel(...)` returns
- sleep-based cooperative windows before expensive fan-out
- separate progress callbacks and realtime event projection

That is too much local machinery for a common long-running workflow shape.

### 6. Agent-wide event naming

The project created `AgentWideEventEmitter` so stage and pipeline wide events were queryable by concrete stage name. This was a practical observability improvement but should ideally not require subclassing emitter internals.

### 7. Tool runtime, approvals, and streaming projection

The assistant path built a substantial local tool runtime in [tools.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/assistant/workflows/tools.py).

It owns:

- persisted tool call rows
- approval waits and decisions
- realtime `tool.started`, `tool.updated`, `tool.completed`, `tool.failed` events
- dispatch to domain services
- subpipeline execution for generation tools
- generation stream subscription and merge logic
- child-run linkage

This is exactly the sort of machinery a production tool framework should absorb.

## Agent Deep Dive

## What Stageflow Docs Recommend

The current docs position the reusable agent runtime as a JSON-contract loop.

In [guides/agents.md](/home/antonioborgerees/coding/stageflow/docs/guides/agents.md#L58), the core contract is:

- model emits `{"tool_calls": [...]}`
- or model emits `{"final_answer": "..."}`

The same guide recommends wrapping that runtime in `AgentStage`.

The older examples in [examples/agent-tools.md](/home/antonioborgerees/coding/stageflow/docs/examples/agent-tools.md#L84) are even further from production reality:

- parse intent manually
- convert it into custom `Action` objects
- run registry tools directly
- synthesize a response in-process

That is fine as a teaching aid, but it is not the right abstraction for a backend that already has provider-native function calling available.

## What SoftSkills Actually Needed

The real assistant runtime in [assistant/workflows/service.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/assistant/workflows/service.py#L607) does this instead:

- calls the provider with native tool definitions via `complete_with_tools(...)`
- receives provider-native tool calls
- validates them against typed Pydantic contracts
- emits durable `tool.invoked` events
- executes tools in parallel
- persists tool-call rows
- waits for approvals when needed
- feeds sanitized tool results back into the next model turn
- handles cancellation at loop boundaries
- separates planning/tool use from final streamed answer generation

The admin agent is also revealing. In [admin_agent/workflows/service.py](/home/antonioborgerees/df/soft-skills/backend/src/soft_skills_backend/modules/admin_agent/workflows/service.py), the `AGENT` stage is only the planning stage. Tool execution is an ordinary guarded work stage. That means the real value came from Stageflow orchestration, not from Stageflow agent primitives.

## What We Worked Around

### Native tool calling was outside the Stageflow agent abstraction

This was true at review time. It is no longer fully true as of 2026-04-11.
Stageflow now has a native-first tool runtime boundary, but SoftSkills still
keeps its own assistant loop policy and persistence/projection concerns around
that boundary.

### Tool execution needed persistence and realtime state, not just execution

The tool executor had to persist rows, emit websocket updates, wait for approvals, and attach child workflow lineage. A simple tool registry abstraction was too narrow.

### Final answer streaming needed a separate path

The assistant does not just "finish the loop" with a JSON final answer. It performs a later streaming response step. That is a real production requirement and should be reflected in the framework design.

### Agent cancellation was orchestration-sensitive

The assistant and generation flows needed cancellation to propagate into active tasks and child runs. That behavior lived in application code, not in Stageflow agent or tool abstractions.

### Observability was split across durable events and realtime broker events

SoftSkills had to deliberately separate:

- durable Stageflow-style events like `tool.invoked`
- UI-focused stream events like `tool.started` and `tool.completed`

That split is legitimate, but the framework should offer a cleaner model for it.

## Why The Current Agent Abstraction Misses The Boundary

The current Stageflow agent story is centered on "how an agent loop works internally." The production need is "how a backend coordinates a provider-native tool-calling runtime inside a larger observable workflow."

That is the wrong center of gravity.

For production backend use, the framework should start from these assumptions:

- the provider may already support native tool calling
- tool requests should stay in provider-native form as long as possible
- tool calls need typed validation before execution
- execution may require approvals, persistence, or child workflows
- agent runs need durable observability and cancellation hooks
- final user response may be streamed separately from the planning/tool loop

## What Should Move Into Stageflow

## 1. Native Tool-Calling Agent Runtime

This was the top priority and is now substantially shipped.

Stageflow now provides a first-class reusable runtime that:

- accepts provider-native tool definitions
- calls providers through native tool-calling APIs
- parses provider-native tool call responses directly
- validates tool arguments against typed contracts
- supports parallel tool execution
- supports approval hooks
- emits durable tool lifecycle events
- supports cancellation checkpoints between iterations
- optionally hands off final response generation to a separate streaming responder

This now replaces the JSON envelope contract as the primary recommendation. The
JSON loop should remain only as fallback or testing mode.

## 2. First-Class Logged Subpipeline Execution

Move the local subpipeline wrapper pattern into the framework:

- spawn child pipelines with correlation and request metadata
- preserve selected `ctx.data` keys safely
- inherit or override timeout budgets explicitly
- preserve parent stage and run lineage
- emit child run lifecycle logs automatically

This is now shipped for both single and parallel child runs.

Stageflow now provides:

- `run_logged_subpipeline(...)` for one child run
- `LoggedSubpipelineRequest` for declarative child-run configuration
- `run_logged_subpipelines(...)` for bounded-concurrency child-run fan-out with
  ordered results and optional fail-fast scheduling

SoftSkills no longer needs to keep framework-shaped child-run logging glue just
to make subpipelines production-safe.

## 3. Typed Stage Output Helpers

Add first-class typed stage payload helpers so application code does not keep reinventing:

- a payload + summary result envelope
- typed payload extraction from upstream stage inputs
- typed payload extraction from final results
- standard `ok/cancel/fail` helpers with summary metadata

This would materially reduce boilerplate across practice, progression, evaluation, catalog, and assistant code.

## 4. Cancellation Checkpoints And Stage-Start Hooks

Add explicit stage-level runtime helpers such as:

- `ctx.raise_if_cancelled()`
- `await ctx.cancellation_checkpoint()`
- before-stage-start hooks for observability and progress publication

Long-running workflows should not need sleep-based cancellation windows before fan-out.

## 5. Prompt Render And Typed LLM Stage Builders

Stageflow should offer reusable builders for a very common pattern:

- request/guard stage
- prompt render stage
- typed LLM transform
- output guard / semantic validation

The prompt registry itself can remain pluggable, but the orchestration pattern is generic and recurring.

## 6. Tool Execution Runtime With Persistence Hooks

The framework now has a reusable execution/runtime boundary, but it still needs
stronger persistence-aware integration for production host apps.

Stageflow should continue evolving beyond "execute with approval features" into
a runtime that can integrate:

- persistence callbacks
- lifecycle event hooks
- approval resolvers
- child workflow execution
- tool-specific timeout policies
- result sanitization and formatting hooks

That would absorb a large part of the custom assistant tool runtime.

## 7. Better Event Projection For UI-Facing Workflows

Stageflow should support ordered projections or projection hooks for workflows that also power a live UI stream. SoftSkills had to build its own durable sequence logic around parallel execution.

## 8. Fix Callable Stage Typing

The installed runtime accepts async callable stage runners, but the typing still forces repeated `cast(Any, ...)` across the codebase. This is straightforward framework debt and should be fixed.

## What Should Probably Stay Outside Stageflow

- domain algorithms like progression math and recommendation scoring
- SQL guardrails and app-specific secure query semantics
- app-specific prompt registries and governance rules
- app-specific realtime broker adapters
- app-specific persistence schemas for turns, tool calls, and generated artifacts

Stageflow should absorb orchestration mechanics, not product semantics.

## Improvement Plan

## Phase 1: Fix The Foundation

Ship these in Stageflow first:

1. Native tool-calling agent runtime and stage
2. First-class logged pipeline and subpipeline helpers with context-data propagation
3. Callable stage typing fixes
4. Typed stage-result helpers

Impact:

- removes the biggest local platform wrapper
- makes agent support viable for production backends
- reduces boilerplate across nearly every pipeline

Status:

- items 1, 2, 3, and 4 are now materially complete

## Phase 2: Improve Long-Running Workflow Ergonomics

Add:

1. cancellation checkpoints
2. stage-start hooks
3. ordered event projection hooks
4. richer tool executor lifecycle hooks

Impact:

- simplifies generation and assistant cancellation
- improves UI-facing observability
- reduces local event and broker glue

## Phase 3: Raise The Abstraction Level Carefully

Add optional builders for:

1. prompt render -> typed LLM -> guard templates
2. worker-fanout subpipeline templates
3. reusable progress reporting helpers

Impact:

- improves reuse without turning Stageflow into a business-logic framework

## Practical Guidance For SoftSkills Right Now

- Keep using Stageflow for DAG orchestration and subpipeline topology.
- Keep adopting extracted Stageflow surfaces where the boundary is genuinely
  reusable: typed tool contracts, runtime I/O, lifecycle hooks, and approval
  backend interfaces.
- Do not force a full assistant rewrite onto `Agent` if the remaining app-owned
  persistence and streaming concerns would just be restitched locally.
- Keep prompt render stages and durable projection logic centralized until
  Stageflow grows the missing primitives.

## Final Assessment

Stageflow succeeded here as an orchestration framework.

At review time it did not succeed as a production agent framework. That is no
longer the full picture.

The strongest evidence is simple:

- SoftSkills uses Stageflow everywhere for workflow coordination.
- SoftSkills previously used almost none of Stageflow's higher-level
  agent/tool runtime for the actual assistant.
- The most reusable parts of that local assistant runtime have now started to
  move into Stageflow and survive real-provider validation in SoftSkills.

That is the roadmap signal. The next Stageflow gains should continue absorbing
the operational scaffolding SoftSkills still has to build around orchestration,
especially durable persistence hooks, ordered projection, stage-scoped
idempotency, and prompt/LLM stage builders.

## Recommended Next Sprint (2026-04-12)

The next extraction target should be durable tool lifecycle persistence and
projection hooks.

Why this should be next:

- the native tool runtime boundary is now proven in real-provider-backed use
- logged parent/child execution is now framework-native
- the largest remaining reusable gap is still the app-owned persistence and UI
  projection glue around tool lifecycle state

That sprint should aim to add:

1. persistence-aware lifecycle callbacks for `tool.invoked`,
   `tool.started`, `tool.updated`, `tool.completed`, and `tool.failed`
2. projection and ordering hooks so UI-facing workflows can consume a
   framework-level event stream without restitching sequencing logic
3. stage-scoped idempotency and event naming/queryability improvements, since
   SoftSkills still carries those as framework-shaped local wrappers

After that, the next candidate should be prompt-render and typed-LLM stage
builders.
