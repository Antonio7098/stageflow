








## Roadmap (UCP + Stageflow as standalone frameworks) toward “the DB layer” + USEP vision

You’ve already converged on a **very strong split**:

- **UCP** = canonical content semantics + deterministic mutation/query primitives (UCM/UCL/UCQ)
- **Stageflow** = execution substrate (pipelines, policy gates, budgets, observability, replayable runs)
- **DB layer** = optional-but-first-class persistence + indexing + federation, exposed *only* through UCP abstractions

Stageflow already enforces several of the USEP non‑negotiables (run model, interceptors, event sinks, immutable [ContextSnapshot](cci:2://file:///home/antonio/programming/stageflow/stageflow/context/context_snapshot.py:40:0-446:9)). @/home/antonio/programming/stageflow/README.md#86-173 @/home/antonio/programming/stageflow/project/stageflow.md#82-91 @/home/antonio/programming/stageflow/stageflow/context/context_snapshot.py#41-49

UCP already covers the canonical content IR + deterministic block IDs, and an agent-friendly mutation language (UCL). @crates/ucm-core/src/id.rs#205-260 @crates/ucl-parser/src/lib.rs#1-39

The roadmap below is structured so you **don’t accidentally turn UCP into “a database”**; instead you add a DB-backed implementation *behind* stable interfaces.

---

# 1) Target architecture boundaries (what owns what)

## **UCP owns (library-level semantics)**
- **Data model**: `Block`, [Document](cci:2://file:///home/antonio/programming/unified-content-protocol/crates/ucm-core/src/document.rs:192:0-216:1), `Edge`, metadata, deterministic IDs, normalization. @crates/ucm-core/src/lib.rs#27-49
- **Mutation & validation**: UCL → operations → engine. @crates/ucp-api/src/lib.rs#26-33
- **Graph traversal semantics** (local graph) and *portable traversal ops* (what traversal *means*). @crates/ucm-engine/src/traversal.rs#143-193
- **(Missing today) Query language**: UCQ AST + execution semantics.

## **Stageflow owns (execution substrate)**
- Pipeline DAG composition and execution. @/home/antonio/programming/stageflow/README.md#88-128
- Interceptors as the enforcement point for auth/policy/budgets/timeouts. @/home/antonio/programming/stageflow/project/stageflow.md#116-128
- Durable run/event model and replay (conceptually already in the design). @/home/antonio/programming/stageflow/project/stageflow.md#82-91
- Stages that call **UCP operations** or **UCP queries** as payload.

## **DB layer owns (implementation, not semantics)**
- Persistence, indexing, caching (“reflections”), multi-tenant storage, vector index integration, graph store integration, etc.
- It must present itself as **UCP adapters** and be driven by Stageflow.

---

# 2) The “missing keystone”: a stable UCP Adapter + Planner interface

To keep this whole system clean, the next work should be: **standardize the contract** between Stageflow ↔ UCP ↔ storage backends.

## **Milestone A: UCP “semantic ops API” (portable)**
Create a small set of *semantic* operations that can be:
- executed against in-memory [Document](cci:2://file:///home/antonio/programming/unified-content-protocol/crates/ucm-core/src/document.rs:192:0-216:1) (today)
- executed against DB-backed stores (future)
- executed against federated sources (future)

At minimum you need:
- **ReadOps**: fetch block/doc/subtree, list by tag/role/label, fetch edges.
- **WriteOps**: apply `Operation` batches (what you already have), with atomicity.
- **TraverseOps**: depth-limited graph traversal with filters (already modeled in traversal engine).
- **SearchOps**: (later) vector/hybrid search returning [BlockId](cci:2://file:///home/antonio/programming/unified-content-protocol/crates/ucm-core/src/id.rs:32:0-32:62) + payload.

And you need:
- **Capability discovery**: what can this backend do? (pushdowns, vector support, transactional semantics, etc.)

This is the foundation for BYODB without contaminating Stageflow with DB details.

---

# 3) Phased roadmap (each phase ends with something shippable)

## Phase 1 — “UCP becomes platform-pluggable”
**Goal:** UCP can run in-memory *and* behind a storage interface, without changing UCM semantics.

- **Deliverable 1.1 (UCP): `ucp-store` trait layer**
  - `UcpStore` interface (read/write/traverse/search + `capabilities()`).
  - First implementation: `InMemoryStore` that wraps today’s [Document](cci:2://file:///home/antonio/programming/unified-content-protocol/crates/ucm-core/src/document.rs:192:0-216:1) + `Engine`.
- **Deliverable 1.2 (UCP): stable “execution context” struct**
  - `ActorContext` / `RequestContext` (org_id/user_id/request_id/budgets).
  - Thread it through API boundaries (doesn’t need to change core types yet).
- **Deliverable 1.3 (Stageflow): a minimal UCP stage pack**
  - Stages like `UcpApplyOpsStage`, `UcpTraverseStage`, `UcpGetBlockStage`.
  - These stages do not know *which* store is behind UCP.

**Why first?** Because it forces the separation you want, early, and makes every later feature (DB, federation, vectors) a drop-in adapter.

---

## Phase 2 — “Durability = event log + replay” (before Temporal)
**Goal:** exactly what your Stageflow 2.0 doc says: every run reconstructible. @/home/antonio/programming/stageflow/project/stageflow.md#82-91

- **Deliverable 2.1 (Stageflow): canonical event schema + persistence**
  - Solidify event sink requirements (append-only, monotonic seq, correlation ids).
- **Deliverable 2.2 (UCP): operation journal format**
  - Persist `Operation` batches with metadata (who/why/when/model/version).
- **Deliverable 2.3 (Bridge): replay runner**
  - Rebuild UCP state from snapshot + op journal to reproduce outcomes.

**This gives you most of USEP’s “durable execution / provenance / time-travel debugging”** without the operational complexity of Temporal.

---

## Phase 3 — UCQ: make “query” real (and planner-friendly)
Right now UCQ is in the docs/spec but not implemented in crates. @PROPOSAL.md#16-18

**Goal:** define queries as a stable intermediate representation that can be planned/pushed down later.

- **Deliverable 3.1 (UCP): `ucq-parser` + `ucq-ast`**
- **Deliverable 3.2 (UCP): `ucq-engine` interpreter over in-memory Document**
  - Use [DocumentIndices](cci:2://file:///home/antonio/programming/unified-content-protocol/crates/ucm-core/src/document.rs:89:0-98:1) and [TraversalEngine](cci:2://file:///home/antonio/programming/unified-content-protocol/crates/ucm-engine/src/traversal.rs:143:0-145:1) as execution primitives. @crates/ucm-core/src/document.rs#88-189 @crates/ucm-engine/src/traversal.rs#161-193
- **Deliverable 3.3 (UCP): `explain()`**
  - Return an execution plan tree (even if it’s trivial initially).
  - This becomes the “planner IR” Stageflow can reason about for budgets.

This phase is critical because it turns “UCP as a canonical semantic layer” into something Stageflow can *query*, not just mutate.

---

## Phase 4 — “DB layer v1”: one concrete backend that proves the architecture
Pick one “managed DB” starting point. The simplest that covers a lot:
- **Postgres + pgvector** (relational + vector in one system)

**Goal:** implement a `PostgresUcpStore` adapter that supports a subset of ops.

- **Deliverable 4.1:** schema to persist [Document](cci:2://file:///home/antonio/programming/unified-content-protocol/crates/ucm-core/src/document.rs:192:0-216:1)/`Block`/`Edge` (+ indices)
- **Deliverable 4.2:** atomic apply of operation batches (transaction)
- **Deliverable 4.3:** basic UCQ pushdown for metadata/tag/label queries
- **Deliverable 4.4:** vector payload mapping ([BlockId](cci:2://file:///home/antonio/programming/unified-content-protocol/crates/ucm-core/src/id.rs:32:0-32:62)/[DocumentId](cci:2://file:///home/antonio/programming/unified-content-protocol/crates/ucm-core/src/document.rs:14:0-14:34) as payload)

At this point you have:
- Stageflow orchestrating runs
- UCP providing canonical semantics
- A DB-backed implementation that supports both

---

## Phase 5 — Federation + reflections (“BYODB becomes real”)
Only after UCQ exists and one DB adapter exists.

**Goal:** “adapter ecosystem” + caching/reflection strategy.

- **Deliverable 5.1 (UCP): connector protocol**
  - “scan/discover/capabilities”
- **Deliverable 5.2 (DB layer): reflection/materialization jobs**
  - Stageflow pipelines that periodically ingest external sources into UCM blocks.
- **Deliverable 5.3 (UCP planner): cost model hooks**
  - Estimate cardinality, latency, token cost for semantic queries.

This is where your USEP Calcite/Trino inspirations can start being used pragmatically, but you’ll already have the IR boundaries.

---

## Phase 6 — “Magical DX” (Convex-like) *on top*
Do this after the core contracts and at least one DB adapter exist.

- Reactive subscriptions require:
  - a durable event stream (Phase 2)
  - query IR and dependency tracking (Phase 3)
  - stable store adapter events (Phase 4)

Then build:
- client SDK
- typed query/mutation functions
- reactive invalidation

---

# 4) What you’ve already done that directly supports this roadmap

- **Stageflow already has the right “substrate” shape**:
  - DAG execution + interceptors + event sink protocol + replayable snapshot concept. @/home/antonio/programming/stageflow/README.md#7-13 @/home/antonio/programming/stageflow/project/stageflow.md#82-91
- **UCP already has the right “semantic core”**:
  - deterministic IDs + normalization, block graph, engine operations, traversal. @crates/ucm-core/src/id.rs#205-260 @crates/ucm-engine/src/operation.rs#20-97 @crates/ucm-engine/src/traversal.rs#161-193
- **You already have the “agent command surface”**:
  - UCL parsing into operations is a real advantage; it’s effectively a compact “edit IR”. @crates/ucl-parser/src/lib.rs#1-39

The biggest missing pieces are **UCQ** and the **store/planner interfaces**.

---

# 5) Two high-impact decisions to make now (so the roadmap doesn’t fork)

## 1) What is the unit of persistence?
Pick one as the first-class unit:
- **Document-as-unit** (persist whole doc snapshots + block tables)
- or **Block graph-as-unit** (blocks are global, docs are “views”)

Given current UCP code is document-centric, **Document-as-unit** is the low-risk first step.

## 2) Which backend do you want as DB-layer v1?
To keep iteration speed high:
- **Postgres + pgvector** is the best “first system” (single operational surface area, broad applicability).

---

## Status
- **Completed**: stageflow repo scan + confirmed it already provides the orchestration substrate you describe.
- **Delivered**: phased roadmap with clear milestones and where each feature lives.
- **Next step (your call)**: I can turn Phase 1 into an explicit API sketch (names, types, module layout) for `UcpStore` + the first Stageflow stages that call it.