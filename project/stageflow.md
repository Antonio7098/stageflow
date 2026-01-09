# Stageflow 2.0 — Unified Execution Architecture

## 1. Purpose and Scope
Stageflow is the single execution substrate for Eloquence. Every user-visible action—voice turns, typed chat, document edits, exercises, settings changes—runs through the same Directed Acyclic Graph (DAG), policy gates, and observability surfaces. This document supersedes the original `stageflow.md` with a consolidated, authoritative reference that covers design principles, runtime contracts, content modeling, security posture, error handling, testing, and migration.

### Goals
- **Total execution integrity**: exactly one orchestrator, one DAG, one set of invariants per run.
- **Composable infrastructure**: stages orchestrate, payloads (agents/tools/enrichers/workers) own business logic.
- **Run-centric durability**: every action is reconstructible via `PipelineRun` + `pipeline_events`.
- **Observability-first**: if it is not logged, traced, and replayable, it did not happen.
- **Built-in security and tenancy**: authentication, authorization, policy, audit, and residency are part of the substrate, not bolted on later.

### Out of Scope
- Detailed UI copy and visual styling.
- Provider SDK minutiae (handled in provider-specific docs).
- Legacy pipeline internals except where called out in migration notes.

## 2. Non-Negotiable Principles
1. **Containers vs. Payloads**: Stages own orchestration, timeouts, telemetry, and retries. Agents, tools, enrichers, workers, and providers encapsulate business logic.
2. **Agents as the universal interface**: Agents receive a `ContextSnapshot` and return a `AgentOutput` (assistant message, actions, artifacts). They never touch I/O or infrastructure concerns.
3. **Streaming-first and parallel**: StageGraph fires nodes as soon as dependencies resolve. STT, enrichers, assessments, and workers overlap wherever safe.
4. **Topology / Configuration / Behavior separation**:
   - **Topology** = DAG structure (composed Pipelines), defined in code (Pipeline classes) and costly to change.
   - **Configuration** = provider/model/timeout/enricher wiring, overridable per pipeline.
   - **Behavior** = cheap runtime mindset (practice, roleplay, doc_edit...) read by agents.
5. **Unified Content Model (Block Protocol)**: documents, profiles, exercises, and UI artifacts share the same block schema for precise edits and provenance.
6. **Observability is reality**: lifecycle, stage, tool, and agent events are durably recorded, ordered, and replayable.
7. **Policy and tenancy everywhere**: authentication, org isolation, and policy checks are enforced via interceptors before and after every critical operation.

## 3. Architectural Stack
```
Client → API → Entry Router → Pipeline → PipelineOrchestrator → StageGraph
                                              │
                                              ├─ Pipeline (Stage definitions + composition)
                                              ├─ Interceptors (auth, policy, metrics, logging…)
                                              ├─ Stages (declared inputs/outputs)
                                              ├─ Agents (plans) & Workers (background)
                                              └─ Event sinks → Projector → Client
```

### 3.1 Layers
| Layer | Responsibilities |
|-------|------------------|
| **Core substrate** | Stage protocol, StageGraph, PipelineContext, PipelineOrchestrator, interceptors, event sinks, projector. |
| **Agents & Tools** | Agent registry, dispatcher/router contracts, tool schemas, deferred streaming, delegation helpers. |
| **Domains** | Voice, chat, documents, assessment, memory, exercises – built entirely on Stageflow. |
| **Infrastructure** | Provider registry, ports, logging, tracing, storage, audit pipelines. |

### 3.2 Data & Control Flow
- **Control**: Client → Router → Orchestrator → StageGraph → Event sink → Projector → Client.
- **Data**: Input (audio/text) → enrichers → `ContextSnapshot` → Agent plan → ToolExecutor → artifacts/documents/memory → persistence + metrics.

## 4. Runtime Contracts

### 4.1 Conversational Contract
| Requirement | Notes |
|-------------|-------|
| Exactly one `chat.complete` per user-originated turn | Applies to voice, text, and manual mode. |
| Optional streaming tokens | `chat.token`, `voice.audio.chunk`, `ui.artifact`. |
| Tool telemetry | `tool.invoked`, `tool.started`, `tool.completed`, `tool.failed`, `tool.undone`, `tool.undo_failed`. |
| Error surfacing | `error.*` events reference `pipeline_run_id` + `request_id`. |
| Operational runs | May emit `status.update` instead of `chat.complete`. |

### 4.2 Lifecycle Contract
States: `created → running → completed|failed|canceled`. Cancellation requires explicit `pipeline.cancel_requested`. Failed runs still persist `PipelineRun` + `error_summary` and often a DLQ entry.

### 4.3 Topology-Driven Execution
- Topology defines which stages run sequentially vs. in parallel (e.g., `fast_kernel` vs. `accurate_kernel`).
- Configuration toggles providers/models/timeouts/enrichers per stage.
- Behavior is a runtime hint passed to agents; switching behavior is cheap, switching topology is expensive (`SwitchTopologyAction`).

### 4.4 Tenancy & Safety (A1)
- `org_id` enforced across `pipeline_runs`, events, artifacts, documents, and memory writes.
- PolicyGateway enforces pre-LLM, pre-action, and pre-persist checkpoints.
- Auth, org, and region interceptors run before any stage logic.

### 4.5 Reliability (A2)
- No stage may block indefinitely; timeouts + retries + fallbacks are standardized interceptors.
- Provider call failures feed structured metrics and circuit breakers.
- Systemic failures create DLQ items linked to `pipeline_run_id` for ops intervention.

## 5. Durable Run Model
| Entity | Purpose |
|--------|---------|
| **PipelineRun** | Identity, selection (pipeline/kernel/channel/behavior), timestamps, outcomes (STT result, routing decision, assessment state, error summary). |
| **pipeline_events** | Append-only structured events (stage.*, agent.*, tool.*, chat.*, voice.*, ui.*, error.*). Ordered via monotonic sequence per run. |
| **provider_calls** | LLM/STT/TTS/db call metadata (latency, tokens, status). |
| **artifacts** | Durable UI payloads (`tool_state`, `document_diff`, `chart`, etc.). |
| **approval_requests** | HITL approvals for risky actions (doc edits, profile changes, memory writes). |
| **dlq_items** | Recorded systemic failures requiring human review. |

## 6. Stage Substrate & Orchestration

### 6.1 Stage Protocol & Context
```python
class Stage(Protocol):
    name: str
    kind: StageKind  # TRANSFORM | ENRICH | ROUTE | GUARD | WORK | AGENT
    async def execute(self, ctx: StageContext) -> StageOutput: ...
```
`StageContext` exposes immutable inputs, injected ports, runtime configuration, and an append-only event buffer. Stages declare inputs/outputs via `StageSpec`; `ContextBag` rejects duplicate keys to prevent data races.

### 6.2 StageGraph Execution
- `StageSpec` defines `name`, `runner`, `dependencies`, `inputs`, `outputs`, `args`.
- Graph executor runs eligible nodes concurrently, merges outputs immutably, emits events per stage.
- DAG validation ensures every input has a producer and no cycles exist.

### 6.3 PipelineOrchestrator
Responsibilities:
- Lifecycle transitions (`created → running → terminal`).
- StageGraph scheduling and cancellation propagation.
- Interceptor invocation order (before/after/on_error).
- Structured event emission (`pipeline.*`, `stage.*`, `llm.*`, `tool.*`, `chat.*`, `ui.artifact`, `error.*`).
- Interaction with event sinks (database + Central Pulse) and Projector.

### 6.4 Interceptors
Ordered middleware for cross-cutting concerns:
1. Circuit breaker (service health)
2. Tracing (OpenTelemetry spans)
3. Auth check (JWT validation → `AuthContext`)
4. Org enforcement (tenant isolation)
5. Region enforcement (data residency)
6. Policy gateway (A1 safety)
7. Rate limiter (per user/session/org)
8. Metrics (latency, errors, tokens)
9. Logging/Audit (structured JSON + tamper-evident chain)

Interceptors can short-circuit stages, inject observations, request approvals, retry transient errors, or escalate to DLQ.

### 6.5 Parallelism Contracts
- Stages only read declared inputs; undeclared reads fail validation.
- `ContextBag` merges outputs immutably; duplicate keys raise `DataConflictError`.
- Event sequencing uses monotonic counters per `pipeline_run_id` for deterministic replay.
- `_agent_lock` ensures agents re-enter only after concurrent stages finish.

## 7. Pipeline Composition & Routing

### 7.1 Composition System
Pipelines are defined in code as typed classes, replacing static JSON registries. This enables compile-time safety, IDE autocomplete, and explicit composition.

```python
class Pipeline:
    stages: dict[str, StageSpec]
    
    def compose(self, other: 'Pipeline') -> 'Pipeline':
        # Merges stages and dependencies from another pipeline
        ...

    def build(self) -> StageGraph:
        # Generates executable DAG for the orchestrator
        ...
```

| Component | Responsibility |
|------|----------------|
| **Pipeline** | Definition and composition of stages + dependencies. Replaces `kernels.json`, `channels.json`, and `PipelineFactory`. |
| **StageGraph** | Executable DAG generated by `Pipeline.build()`. |
| **Registry** | Simple mapping of names to `Pipeline` instances (replaces `pipelines.json`). |
| **configurations.json** | Provider/model/timeouts/enricher defaults (still JSON for runtime overrides). |
| **agents.json** | Agent definitions (prompt refs, capabilities, streaming mode). |
| **capabilities.json** | Tool schemas, policies, undo metadata. |
| **behaviors.json** | Runtime presets (symbolic hints for interpretation). |
| **dispatchers.json** | Semantic routing logic for agent selection. |
| **workers.json** | Background processor definitions. |

### 7.2 Routing Patterns
| Pattern | Stage | Description |
|---------|-------|-------------|
| **Entry Router** | Pre-pipeline; selects the target `Pipeline` instance. No LLM or enrichers. |
| **Dispatcher** | Inside pipeline | Has full context; selects agent + behavior + sub-dispatchers. Can chain (e.g., doc intent). |
| **Pipeline Switch** | Mid-run | Agent issues `SwitchPipelineAction`; orchestrator finalizes current pipeline, hydrates target pipeline, preserves context. |
| **Internal Router** | Pipeline stage | Branch to sub-agents (e.g., doc edit vs. doc query) without changing topology. |

### 7.3 Workers & Triggers
Workers are non-user-facing WORK stages that process context in parallel to the main agent flow. Like all stages, they execute when their dependencies resolve and can run concurrently with AGENT stages. Workers emit `WorkerResult` (data, events, mutations) but no assistant messages.

## 8. Agents, Tools, Plans, and Deferred Streaming

### 8.1 ContextSnapshot
Immutable agent input containing run identity, normalized messages, enrichments (profile, memory, docs), routing decisions, behavior hints, and metadata. Supports deterministic testing/replay.

### 8.2 AgentOutput
```python
@dataclass
class AgentOutput:
    assistant_message: str | None
    actions: list[Action]
    artifacts: list[Artifact]
    requires_reentry: bool = False
    streaming_mode: Literal["immediate", "deferred"] = "immediate"
```

### 8.3 Actions & Tools
- `Action` references a capability (e.g., `EDIT_DOCUMENT`, `STORE_MEMORY`, `SWITCH_PIPELINE`).
- Tools define name, input schema, handler, policy, undo semantics, artifact behavior.
- ToolExecutor enforces behavior gating, policy approvals, version checks, and artifact emission.

**Single Edit Entry Point**: Document editing uses one `edit()` tool with no complexity parameters. A lightweight routing worker analyzes edit request and selects execution strategy (single-op, multi-op, parallel-planning, or bulk) internally. This keeps conversational agent simple—no need to reason about edit complexity. Routing decisions based on document size, number of target blocks, and edit intent.

### 8.4 Deferred Streaming (Document Editing & Multi-step Workflows)
Two-phase execution for tool-heavy agents:
1. **Internal tool loop (non-streaming)**: Agent issues tool calls via `llm.complete`. UI shows `tool_state` artifacts (`loading → success/error`, undoable). Agent can inspect results before deciding next action.
2. **External response (streaming)**: After tools finish, agent calls `llm.stream` to explain actions to the user.

This model delivers clean UX (no tool syntax leakage), per-tool undo, adaptive planning, and consistent telemetry (`tool.invoked|started|completed|undone`).

### 8.5 Agent Delegation
Conversational agents delegate specialized tasks (e.g., `request_edit`) to non-user-facing agents via a delegator tool that passes the full context snapshot and extra enrichers (document blocks, metadata). Delegate agents return summaries for the calling agent to relay.

### 8.6 Parallel Planning, Serial Writing
For complex document edits, the system uses parallel planning workers that reason independently but commit through a single serialized gate.

**Edit Orchestrator**: Single authority for document mutations. Owns document snapshot, block versions, and commit gate. Never edits content directly.

**Parallel Planning Workers**: Specialized workers (e.g., OpeningWorker, StructureWorker, ToneWorker) receive read-only document snapshots and return proposed operations, not applied edits. Workers never call edit tools, never see live state, never commit.

**Aggregation & Conflict Resolution**: Orchestrator collects all proposals, validates against current snapshot, detects conflicts (same block_id, parent/child clashes, ordering conflicts), and resolves via priority rules, merge logic, or escalation.

**Single Commit**: After aggregation, orchestrator acquires document lock, validates block versions, applies ops atomically, increments document version, and releases lock. Optimistic concurrency checks detect conflicts from other runs.

This pattern separates thinking (parallelizable) from mutating (serialized), preserving block ID guarantees, audit trails, and replayability.

### 8.7 Subpipeline Runs
- **Creation**: When an agent action (e.g., `edit()`, `search()`, delegation) requires its own topology, ToolExecutor asks `PipelineFactory` for the referenced pipeline and PipelineOrchestrator spawns a child `PipelineRun` with its own kernel/channel.
- **Correlation**: Child runs store `parent_run_id`, `parent_stage_id`, and the invoking action’s `correlation_id`. All `pipeline_events`, `provider_calls`, artifacts, and DLQ entries include both IDs so Central Pulse can render run trees and operators can trace failures end-to-end.
- **Isolation & data flow**: Children receive a forked `ContextSnapshot` (read-only view of parent data) and emit their outputs as action results back to the parent StageGraph, keeping ContextBags conflict-free.
- **Lifecycle**: Parent cancellation cascades down; child failures bubble up as `tool.*` events referencing the child `pipeline_run_id`. Retry/abort policy stays with the capability definition, and structured telemetry keeps observability contracts intact.

## 9. Unified Content Model (Block Protocol)

### 9.1 Scope
**Applies to** anything an agent is going to edit.
**Does NOT apply to**: relational business entities (sessions, strategies, assessments, users), system configuration, audit logs, or real-time operational state.

**Content IR Framing**: Blocks are an intermediate representation for user-authored content. Agents operate exclusively on Blocks and emit declarative operations. Projection adapters translate those operations back to authoritative stores (document database, SQL rows, external APIs). This separation keeps agents schema-agnostic and enables swapping storage without retraining. Blocks are NOT the source of truth for relational entities—projection to authoritative stores is required.

**Relational Integration**: Traditional SQL tables stay in their native schemas; we expose them to agents through lightweight mappers that project table rows into UCM blocks when needed (and map block updates back through the same mapper). Only document-style assets live natively in UCM storage.

### 9.2 Hybrid Representation
Blocks describe *what* they are; document `structure` maps define *where* they live.
```json
{
  "document": {
    "id": "doc_sales_script_v2",
    "root": "blk_root",
    "structure": {
      "blk_root": ["blk_intro", "blk_pitch"],
      "blk_intro": ["blk_hook", "blk_value"]
    }
  },
  "blocks": {
    "blk_hook": {
      "type": "paragraph",
      "value": "Hi, thanks for joining me today.",
      "constraints": {"max_length": 1000, "speaking_style": "professional"},
      "metadata": {"version": 3},
      "links": {"derived_from": ["blk_opening_hook"], "owned_by": "doc_sales_script_v2"}
    }
  }
}
```
Benefits: LLM-friendly, token-efficient, concurrent-safe (structure vs. content updates), enables partial fetch and GraphRAG.

### 9.3 Lifecycle
1. Router selects `edit_document` pipeline.
2. Enrichers fetch document blocks + structure.
3. DocAgent plans `EDIT_DOCUMENT` action(s) referencing block IDs.
4. ToolExecutor validates versions, applies operations, creates new `document_version` linked to `pipeline_run_id`.
5. `document_diff` artifact emitted for UI + approval.
6. UI renders diff + per-operation undo buttons.

### 9.4 Validation Rules
| Operation | Validation |
|-----------|------------|
| update | Block exists; `base_version` matches; schema validation passes. |
| append | Parent exists and accepts children; new block ID unique. |
| delete | Block exists; optional cascade; no dangling backlinks. |
| reorder/move | Targets exist; no ancestor loops; container supports ordering. |

### 9.5 Concurrency & Conflict Resolution
- Optimistic concurrency: every mutation carries `base_version`; ToolExecutor raises `VersionConflict` if current version differs.
- Resolution strategies: reject+retry (default), auto-merge for append-only blocks, HITL artifact for high-stakes conflicts.
- Multi-agent editing: parallel analyzers produce proposals; orchestrator serializes commits.

**Conflict Resolution UX**: When `VersionConflict` occurs, system emits conflict artifact with resolution options. User chooses retry (agent refetches and reapplies), overwrite (force commit user's version), or cancel. Conflict artifacts include `block_id`, `user_version`, `current_version`, `conflicting_changes` summary, and suggested resolution based on block type and conflict pattern.

**Auto-Merge Conditions**: Safe only for append-only blocks (logs, comments, list items) where changes are guaranteed non-overlapping. Requires explicit opt-in in block metadata.

### 9.6 Knowledge Graph Overlay
Blocks carry `links` (e.g., `derived_from`, `depends_on`, `owned_by`). Retrieval stages fetch neighborhoods, enabling provenance, dependency tracing, and GraphRAG expansion.

### 9.7 UCM/UCL Alignment with Stageflow
This section defines how UCM (Blocks) and UCL (Unified Content Language) plug into the Stageflow 2.0 substrate. UCM/UCL are **payload protocols**; Stageflow remains the **container/orchestrator**.

#### 9.7.1 Roles and Responsibilities
| Layer | Responsibility |
|-------|----------------|
| **Stageflow (Pipelines/Stages)** | Selects edit pipelines, runs UCL-aware stages (parser, orchestrator, projection), enforces policy, tenancy, and observability. |
| **UCM (Blocks + Structure)** | Canonical internal representation for editable content (documents, projections of SQL rows/files). Agents and tools target blocks, not raw storage. |
| **UCL (Language/Commands)** | Compact, versioned DSL that describes block definitions and edit operations (`EDIT`, `MOVE`, `APPEND`, `EDIT_ROW`, etc.). Produced by agents, consumed by UCL stages. |

Stageflow never executes UCL directly. Instead, it treats UCL as a **typed payload** flowing through specific stages inside an edit pipeline.

#### 9.7.2 Edit Pipelines (Topology)
Stageflow defines explicit pipelines for content mutation, each aligned with UCM block types and UCL verb subsets:
- `edit_document` pipeline → document blocks (headings, paragraphs, lists, code blocks).
- `edit_table` pipeline → `table_row` projections of SQL tables.
- `edit_file` pipeline → `file_range` projections of files/byte ranges.

Each pipeline is a StageGraph composed from a standard edit pattern:
1. **Context Fetch Stage** — uses UCM adapters to fetch relevant blocks + structure (partial neighborhood) for the target doc/table/file.
2. **Agent Stage** — receives `ContextSnapshot` enriched with UCM blocks and emits UCL text (`STRUCTURE`/`BLOCKS`/`COMMANDS` or `COMMANDS` only).
3. **UclParserStage** — parses UCL into an AST/operations list, validates grammar and basic invariants.
4. **EditOrchestratorStage** — maps UCL operations to block-level mutations, performs locking, version checks, aggregation, and atomic commit against UCM storage.
5. **ProjectionStage[document|sql|file]** — translates committed block changes back into authoritative stores (document DB, SQL, files) using projection adapters.
6. **ArtifactStage** — emits `document_diff`, `table_diff`, or `file_diff` artifacts and per-operation undo hooks for the UI.

ToolExecutor continues to provide a **single edit entry point** (e.g., `EDIT_DOCUMENT`, `EDIT_TABLE`, `EDIT_FILE` capabilities) that internally routes to the appropriate edit pipeline. Agents do not select pipelines directly; they call capabilities that Stageflow resolves to pipelines.

#### 9.7.3 UCL as a Typed Payload
Within Stageflow, UCL is treated as a versioned payload with explicit types:
- `ucl_prompt_v1`: raw UCL text from agents.
- `ucl_ast_v1`: parsed, validated representation from `UclParserStage`.
- `ucl_ops_v1`: normalized operation list consumed by `EditOrchestratorStage`.

Pipelines declare which UCL version they expect via configuration (e.g., `ucl_version="v1"`). This allows future grammar evolution by updating pipeline topology/configuration without changing agents, as long as the agent contract (prompt format) remains compatible.

#### 9.7.4 Observability and Policy Integration
UCM/UCL execution obeys Stageflow’s existing observability and policy invariants:
- **Events**: Each UCL operation generates `tool.*` events (`tool.invoked|started|completed|failed|undone`) with `pipeline_run_id`, `request_id`, and block IDs.
- **PolicyGateway**: Intercepts before and after UCL execution to enforce content safety (A1), tenancy (`links.owned_by`), and immutable block rules.
- **DLQ**: Parser failures, projection errors, or systemic edit issues emit `error.*` + `dlq_items` linked to the run.

These hooks ensure that UCM/UCL edits participate fully in Stageflow’s durability, audit, and replay model.

#### 9.7.5 Parallel Planning, Serial Commit (UCL Edition)
Parallel planning workers (StructureWorker, ToneWorker, TableWorker, etc.) operate on **read-only UCM snapshots** and output proposed UCL operations, not direct mutations. The pattern is:
1. Workers receive snapshot + block IDs and emit `ucl_ops_v1` proposals.
2. EditOrchestrator aggregates proposals, resolves conflicts (block_id/version/ordering), and selects the final operation set.
3. A single serialized commit applies the chosen operations through UCM storage and projection adapters.

Workers never call edit capabilities directly and never write to storage; they only propose UCL-level operations. This keeps **thinking parallel, writing serialized**, and preserves Stageflow’s guarantees around total system integrity.

## 10. Behaviors & Stage Interpretation

Behaviors are **runtime mindsets** selected by the entry router or dispatcher and recorded on the `PipelineRun`. They do not redefine topology, stage wiring, or capability policy; those stay in kernels, configurations, agents, and capability registries. A behavior is a single symbolic value that every stage can read from `StageContext.behavior` and interpret locally.

### 10.1 Behavior Registry (`behaviors.json`)
```json
{
  "practice": {
    "agent_id": "practice_agent",
    "display_name": "Coaching Practice"
  },
  "roleplay": {
    "agent_id": "roleplay_agent",
    "display_name": "In-character Simulation"
  },
  "doc_edit": {
    "agent_id": "document_agent",
    "display_name": "Document Editing"
  }
}
```
- `agent_id` is required; it tells the AgentStage which conversational payload to load.
- Additional lightweight metadata (display name, description) is optional and used for analytics or UI surfacing.
- No execution, tool, or assessment policy is encoded here—if policy changes, update the relevant agent or capability definition instead of mutating behavior.

### 10.2 Stage Interpretation Contract
Every stage receives the same `behavior` value. Each stage decides how (or whether) that value influences its execution without relying on centralized behavior-specific configuration.

```python
class AgentStage(Stage):
    DEFAULT_AGENT = "default_agent"
    BEHAVIOR_AGENT_MAP = {
        "practice": "practice_agent",
        "roleplay": "roleplay_agent",
        "doc_edit": "document_agent",
    }

    async def execute(self, ctx: StageContext) -> StageOutput:
        agent_id = self.BEHAVIOR_AGENT_MAP.get(ctx.behavior, self.DEFAULT_AGENT)
        agent = self.agent_registry.get(agent_id)
        return await agent.run(ctx.snapshot)


class AssessmentWorker(Stage):
    MODE_BY_BEHAVIOR = {"practice": "background", "roleplay": "deferred"}

    async def execute(self, ctx: StageContext) -> StageOutput:
        mode = self.MODE_BY_BEHAVIOR.get(ctx.behavior, "background")
        return await self.assessment_runner.run(ctx.snapshot, mode=mode)
```

**Guidelines**
1. **Single source of truth**: If a stage needs behavior-specific logic, encode the mapping inside that stage (or its configuration), not inside behavior definitions.
2. **Safe defaults**: Stages must have default behavior to remain substitutable when new behaviors are introduced.
3. **Observability**: Stages should log the effective interpretation (`"assessment_mode": "deferred"`) to keep runs debuggable.

### 10.3 Enforcement & Policy Placement
- **Agent capabilities** (allowed tools, streaming mode, modality) live in `agents.json`.
- **Tool policy** (schema, approval requirements, undo semantics) lives in `capabilities.json`.
- **Kernel/channel configuration** (enrichers, providers, workers, timeouts) lives in `kernels.json`, `channels.json`, and `configurations.json`.
- **Behavior** is limited to selecting an agent and providing a symbolic hint; policy decisions reference the authoritative registries above.

`ToolExecutor` therefore enforces capability policy strictly based on the agent and tool definitions, not on behavior metadata. If an agent cannot call a capability, it is removed from the agent’s capability list or the capability requires approval globally.

### 10.4 Modal Agents
Modal semantics (e.g., roleplay, simulations) are properties of the agent, not the behavior. When `behavior = "roleplay"` the behavior simply selects the `roleplay_agent`, whose definition includes:
- `modal: true`
- `exit_signal`: tool or action that ends the mode
- Capability constraints (no document edits, no topology switches) enforced by the agent and ToolExecutor

The orchestrator observes the agent’s modal metadata to suspend other conversational agents until the modal agent emits its exit signal. This keeps behavior lean while still enabling complex mode management.

## 11. Security, Tenancy, and Residency

### 11.1 Interceptor Chain
1. **AuthInterceptor** (JWT validation via Clerk/WorkOS → `AuthContext`).
2. **OrgEnforcementInterceptor** (ensures resource `org_id` matches `AuthContext.org_id`).
3. **RegionEnforcementInterceptor** (data residency compliance).
4. **PolicyGateway** (content safety, tenancy, memory write rules).

### 11.2 AuthContext & OrgContext
```python
@dataclass
class AuthContext:
    user_id: str
    email: str | None
    org_id: str | None
    roles: list[str]
    session_id: str

@dataclass
class OrgContext:
    org_id: str
    tenant_id: str
    plan_tier: Literal["starter","pro","enterprise"]
    features: list[str]
```

### 11.3 Tenant Isolation Models
- Row-level security (preferred where supported).
- Application-level filters for multi-tenant databases without RLS.
- Schema/database isolation for regulated tenants.
- PolicyGateway denies any cross-tenant access attempt.

### 11.4 Audit Logging
Mandatory events: `auth.login|logout|failure`, `tenant.access_denied`, `data.read|write|export`, `pipeline.started`, `pipeline.topology_switch`. Audit events include integrity hashes forming a tamper-evident chain.

### 11.5 Data Residency
Region tagging per record (`created_region`, `last_accessed_region`). Region enforcement logs violations and blocks access when requested region differs from record region.

## 12. Observability & Projector

### 12.1 Event Sink & Central Pulse
- `pipeline_events` stored with sequence numbers, timestamps, metadata.
- Central Pulse replays runs, visualizes DAG execution, and correlates provider calls with UI symptoms.

### 12.2 Projector Responsibilities
- Translate events into WebSocket payloads: `status.update`, `voice.transcript`, `chat.token`, `voice.audio.chunk`, `ui.artifact`, `assessment.*`, `error`.
- Guarantee terminal events (`pipeline.completed|failed|canceled`) are emitted last.

## 13. Error Taxonomy & Handling

### 13.1 Categories
| Category | Examples | Handling |
|----------|----------|----------|
| Transient | Provider timeouts, rate limits | Retry with exponential backoff + optional fallback provider. |
| Permanent | Invalid API key, malformed request | Fail-fast, surface error, no retry. |
| Logic | Missing inputs, invalid state, duplicate outputs | Fail-safe, emit error event, fix code. |
| Systemic | Database outage, circuit breaker open | DLQ + alert ops, fail run. |
| Policy | Content violation, cross-tenant access | Fail-safe with explanation. |

### 13.2 StageflowError Schema
Includes category, code, user-safe message, retryability, backoff hints, stage name, `pipeline_run_id`, timestamp, context, and optional fallback target.

### 13.3 Handling Flow
```
Stage executes
   │
   ├─ Success → continue
   │
   └─ Error → classify →
        ├─ Retryable? yes → backoff → retry (capped)
        ├─ Fallback target? yes → switch provider → retry
        └─ Otherwise → emit error event → fail stage → fail pipeline → DLQ if systemic
```

### 13.4 Error Code Families
- `PROV_*`: provider issues (LLM/STT/TTS/db).
- `STAGE_*`: stage-level logic/timeouts.
- `AGENT_*`: agent plan/tool errors.
- `POL_*`: policy/tenancy violations.
- `PIPE_*`: orchestration/lifecycle failures.
Each code documents category, retryability, and handling strategy.

## 14. Testing Strategy

### 14.1 Pyramid
```
E2E (10–20) — full user journeys
Integration (substrate + domain) (50–100)
Integration (substrate only) (30–50)
Domain tests (agents/tools/enrichers) (200–500)
Substrate unit tests (100–200)
```

### 14.2 Guidelines
- Substrate tests are contracts (no external dependencies, <50 ms).
- Domain tests mock the substrate and focus on behavior, not infrastructure.
- Property-based tests cover DAG validity, behavior passthrough.
- Contract tests ensure stages emit start/complete events, ContextBag rejects duplicates, events have required fields.
- Fault-injection tests simulate provider outages, cancellations, memory pressure.
- Performance tests enforce latency budgets per kernel and confirm parallel stages truly overlap.

## 15. Migration Roadmap

### 15.1 Implementation Audit (Dec 2025)
| Component | Status |
|-----------|--------|
| PipelineContext, StageGraph, Orchestrator, EventSink, Provider ports | Complete |
| ContextSnapshot, AuthInterceptor/AuthContext, DLQ implementation, per-provider circuit breakers | In progress |
| Behavior field standardization, StageStatus expansion, Interceptor base class | Pending |

### 15.2 Phased Plan
1. **Fill critical gaps**: ContextSnapshot, auth interceptors, ContextBag conflict detection.
2. **Align patterns**: formal Interceptor base class, behavior standardization, StageStatus updates.
3. **Complete testing**: add property-based, contract, and fault-injection suites.
4. **Operational readiness**: DLQ pipelines, provider circuit breakers, ADR documentation.

### 15.3 Verification Checklist
- [ ] Every stage returns `StageOutput` with status + declared outputs.
- [ ] Every stage emits `stage.{name}.{started|completed|failed}`.
- [ ] Every run reaches a terminal lifecycle state.
- [ ] All provider calls go through ports + registry.
- [ ] PolicyGateway gates all mutation points.
- [ ] Behavior gating enforced before tool execution.
- [ ] No hardcoded providers inside stages (ports only).
- [ ] Tests pass with mock providers (no real API dependency).

## 16. Glossary
| Term | Definition |
|------|------------|
| **Pipeline** | Code-defined class (Stage definitions + composition); replaces `kernels.json`, `channels.json`, and `PipelineFactory`. |
| **Stage** | DAG node with declared inputs/outputs/dependencies. Container, not logic. |
| **Agent** | Payload that plans assistant messages + actions; never handles I/O. |
| **Worker** | Background processor (assessment, memory write) producing data/events, not user messages. |
| **ContextSnapshot** | Immutable agent input built from enrichers and routing decisions. |
| **PipelineContext** | Runtime container for stage execution (data bag, ports, events, interceptors). |
| **Block** | Atomic content unit (id, type, value, constraints, metadata, links) used in the Block Protocol. Constraints specify validation rules per block type (max length, speaking style, format). |
| **Block Document** | Content container with id, root block, and structure map defining block relationships. |
| **Edit Orchestrator** | Single authority for document mutations that coordinates parallel planning workers, aggregates proposals, resolves conflicts, and performs atomic commits. |
| **Behavior** | Runtime mindset controlling execution/tool gating + agent hints. |
| **Pipeline Switch** | Agent-requested pipeline change mid-run; expensive, orchestrator-managed. |
| **Entry Router / Dispatcher** | Pre-pipeline vs. in-pipeline routing components. |
| **Projector** | Converts pipeline events into real-time client updates. |
| **DLQ** | Dead-letter queue for systemic failures requiring human intervention. |

---
Stageflow 2.0 now serves as the definitive reference for engineers, product managers, and operators building on Eloquence. All future architecture decisions, ADRs, and implementation audits should map directly to the sections above. When in doubt, align with the principles, contracts, and invariants in this document before writing code.


TOADD: also have conversation agent call search() find() enritch() to search users files, get more context?
