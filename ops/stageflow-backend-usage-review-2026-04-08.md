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

The framework improvement priority is clear:

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

- A native provider tool-calling agent runtime.
- First-class logged pipeline/subpipeline execution with run-log hooks in the framework core.
- Prompt-render and typed-LLM stage builders.
- Richer persistence-aware tool runtime hooks.
- Ordered UI projection support at the framework level.

### Practical Effect

The framework now absorbs most of the "typed stage ergonomics" and a meaningful
part of the "long-running workflow ergonomics" that SoftSkills previously had to
build locally. The largest remaining gap is still the agent/tool runtime boundary.

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
- `run_logged_subpipeline(...)` reconstructs child context, preserves lineage, logs child runs, and manually rehydrates parent `data`.

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

The number of repeated `StageflowStageResult(...)` wrappers across backend workflows is a signal that the base ergonomics are too low-level.

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

SoftSkills could not use the documented JSON loop because it needed actual provider-native tool calling for reliability and better model behavior. The assistant therefore bypassed Stageflow agent runtime entirely and built its own loop.

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

This is the top priority.

Stageflow should provide a first-class agent runtime that:

- accepts provider-native tool definitions
- calls providers through native tool-calling APIs
- parses provider-native tool call responses directly
- validates tool arguments against typed contracts
- supports parallel tool execution
- supports approval hooks
- emits durable tool lifecycle events
- supports cancellation checkpoints between iterations
- optionally hands off final response generation to a separate streaming responder

This should replace the current JSON envelope contract as the primary recommendation. The JSON loop can remain as a fallback or testing mode.

## 2. First-Class Logged Subpipeline Execution

Move the local subpipeline wrapper pattern into the framework:

- spawn child pipelines with correlation and request metadata
- preserve selected `ctx.data` keys safely
- inherit or override timeout budgets explicitly
- preserve parent stage and run lineage
- emit child run lifecycle logs automatically

SoftSkills should not need local context reconstruction to make subpipelines production-safe.

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

`AdvancedToolExecutor` should evolve beyond "execute with approval features" into a runtime that can integrate:

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
2. First-class logged subpipeline helper with context-data propagation
3. Callable stage typing fixes
4. Typed stage-result helpers

Impact:

- removes the biggest local platform wrapper
- makes agent support viable for production backends
- reduces boilerplate across nearly every pipeline

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
- Keep the assistant on the current custom native tool-calling path for now.
- Do not migrate the assistant to the current `Agent` or `AgentStage` recommendation.
- Treat `StageKind.AGENT` as an observability label today, not as proof that the framework agent abstraction is sufficient.
- Keep prompt render stages, run wrappers, and tool execution infrastructure centralized until Stageflow grows the missing primitives.

## Final Assessment

Stageflow succeeded here as an orchestration framework.

It did not succeed here as a production agent framework.

The strongest evidence is simple:

- SoftSkills uses Stageflow everywhere for workflow coordination.
- SoftSkills uses almost none of Stageflow's higher-level agent/tool runtime for the actual assistant.
- The most complicated and reusable local code exists exactly where Stageflow stops short today.

That is the roadmap signal. The next Stageflow gains should come from absorbing the operational scaffolding SoftSkills had to build around orchestration, especially native tool calling, subpipeline execution, cancellation, and typed stage ergonomics.
