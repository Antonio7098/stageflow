# Stageflow Observability & Dashboard Proposal

**Date:** 2026-03-20  
**Author:** Cascade (w/ @[stageflow] + @[reference/langfuse])

## 1. Executive Summary

Stageflow already exposes rich observability hooks (interceptors, structured events, tracing helpers), but the data mostly flows to logger adapters or downstream user-managed sinks. There is no built-in persistence layer, sampling policy, or UI to inspect agent pipelines end-to-end. Langfuse demonstrates a mature reference implementation that combines standardized ingestion, ClickHouse-backed storage, and interactive dashboards (agent graph, trace explorer, per-user metrics). This document proposes how to bridge the gap by reusing key ideas from Langfuse and delivering a Stageflow-native observability dashboard.

> **Note:** Everything described here is additive. Each component (ingestion worker, storage, dashboard) should ship as an optional plug-in so existing Stageflow deployments can opt in incrementally without breaking changes.

## 2. Current Stageflow Capabilities

| Capability | Where | Notes |
| --- | --- | --- |
| Observability protocols (`PipelineRunLogger`, `ProviderCallLogger`, `CircuitBreaker`) | `@stageflow/stageflow/observability/__init__.py#1-239` | Provides async logging hooks plus correlation helpers, but defaults to no-op implementations. |
| Distributed tracing + correlation IDs | `@stageflow/stageflow/observability/tracing.py#1-358` | Optional OTEL integration with context propagation + `StageflowTracer`. No exporter wiring or standardized span taxonomy yet. |
| Wide events + event sinks | `@stageflow/stageflow/observability/wide_events.py#1-191` and `@stageflow/stageflow/events/sink.py#1-276` | Structured stage/pipeline payloads and sink protocol with logging/backpressure implementations. |
| Built-in interceptors (logging, metrics) | `@stageflow/stageflow/pipeline/interceptors.py#200-259` | Logs start/end + timings, but only to Python logging. |
| Documentation | `@stageflow/docs/guides/observability.md#1-862` | Covers best practices but assumes users run their own sinks/dashboards. |

### Observed Constraints

1. Telemetry is emitted, but Stageflow does not ship a persistence or query surface.
2. There is no packaged UI for visualizing tool chains, parallel branches, or provider costs.
3. Backpressure-aware sinks exist, yet there are no standard metrics exporters or alerting hooks.

## 3. Langfuse Reference Patterns Worth Reusing

| Pattern | Where in Langfuse | Takeaways |
| --- | --- | --- |
| Event ingestion batching + sampling + delayed processing | `@reference/langfuse/langfuse-main/packages/shared/src/server/ingestion/processEventBatch.ts#1-200` | Centralizes queueing, sampling (`isTraceIdInSample`), S3 offload, and ingestion delays to smooth out workloads. |
| Canonical event taxonomy (trace/span/generation/agent/tool/etc.) | `@reference/langfuse/langfuse-main/packages/shared/src/server/ingestion/types.ts#258-643` | Enumerates event types and schemas so downstream storage can stay normalized. |
| Instrumentation helpers bridging OTEL + Datadog + custom metrics | `@reference/langfuse/langfuse-main/packages/shared/src/server/instrumentation/index.ts#1-68` | `instrumentAsync` ensures spans wrap async work and propagate baggage; reusable for Stageflow interceptors. |
| Agent graph data extraction queries | `@reference/langfuse/langfuse-main/packages/shared/src/server/repositories/events.ts#2455-2854` | `getAgentGraphDataFromEventsTable` and `getUserMetricsFromEventsTable` show how to denormalize traces for visualization/analytics. |
| API surface exposing agent graph | `@reference/langfuse/langfuse-main/web/src/server/api/routers/traces.ts#630-699` | tRPC endpoint turns ClickHouse rows into UI-friendly nodes. |
| React hook + visualization components (TraceGraph) | `@reference/langfuse/langfuse-main/web/src/components/trace2/api/useAgentGraphData.ts#1-97` and `@reference/langfuse/langfuse-main/web/src/features/trace-graph-view/components/TraceGraphView.tsx#1-191` | Encapsulates fetching, normalization, and graph rendering with step detection/cycling. |

## 4. Gap Analysis

1. **Data durability:** Stageflow lacks a built-in telemetry store. Langfuse persists every observation (spans, generations, tools) for replay and analytics.
2. **Query APIs:** There are no packaged endpoints to fetch pipeline timelines, agent graphs, or provider metrics. Langfuse exposes tRPC/REST for these.
3. **Dashboard UX:** Stageflow has no UI to inspect DAG execution or tool chains; Langfuse’s Trace Graph gives visual feedback on agent orchestration.
4. **Instrumentation consistency:** Stageflow allows custom interceptors but offers no canonical exporter. Langfuse’s `instrumentAsync` + event schemas ensure consistent spans + metrics.
5. **Observability governance:** There is no sampling/backpressure policy beyond a single queue. Langfuse applies delay windows, sampling, and queue metrics.

## 5. Proposed Implementation Plan

### Phase 0 – Adopt a Canonical Telemetry Contract

1. **Define Stageflow event taxonomy** aligning with Langfuse types (trace, span, generation, tool, agent, evaluator). Start by extending `stageflow.tools.events` to emit `tool.*` lifecycle events already modeled in Langfuse (`eventTypes.TOOL_CREATE`).
2. **Standardize metadata envelopes** (trace/span IDs, pipeline/session/user IDs) inside `WideEventEmitter` payloads to match Langfuse headers. This keeps parity with Langfuse’s `AgentGraphData` expectations.

### Phase 1 – Telemetry Persistence Service

1. **Ingestion worker:** Implement a Stageflow service akin to `processEventBatch` that accepts batched events (OTLP or internal) and forwards them to the storage backend. Reuse backpressure-aware queueing semantics from `stageflow.events.sink.BackpressureAwareEventSink`, but persist to durable storage (ClickHouse/Postgres + S3) following Langfuse’s approach.
   - New module: `stageflow/observability/ingestion/service.py`
   - Reference: `@reference/langfuse/langfuse-main/packages/shared/src/server/ingestion/processEventBatch.ts#1-200`.
2. **Sampling + delay policies:** Mirror Langfuse’s `getDelay` logic to prevent duplicate processing around UTC day boundaries.
3. **Storage schema:** Define tables similar to Langfuse `events_core/events_full` to store normalized pipeline + agent events.

### Phase 2 – Query + API Surface

1. **Analytics repository:** Build query helpers equivalent to Langfuse’s `getAgentGraphDataFromEventsTable` and `getUserMetricsFromEventsTable` for Stageflow’s chosen database.
   - New module: `stageflow/observability/repository.py`.
   - References: `@reference/langfuse/langfuse-main/packages/shared/src/server/repositories/events.ts#2455-2854`.
2. **API endpoints:** Expose queries via FastAPI (or Stageflow’s preferred HTTP surface). Mirror Langfuse’s `getAgentGraphData` tRPC contract to return normalized graph nodes.
   - New file: `stageflow/api/observability.py`.
3. **Telemetry SDK alignment:** Provide an official exporter class that mirrors Langfuse’s instrumentation to ensure spans + events flow into the ingestion worker.

### Phase 3 – Stageflow Observability Dashboard

1. **Frontend app:** Create a lightweight dashboard (Next.js/FastAPI + React) that consumes the new APIs. Start with three views:
   - **Trace / Agent Graph:** Inspired by `TraceGraphView.tsx`, convert pipeline + tool events into nodes/edges showing branching, retries, and parallel runs.
   - **Pipeline Timeline:** Gantt-like view using stage start/end from `WideEventEmitter` payloads.
   - **Provider Metrics:** Surface counts, latency, cost metrics per `ProviderCallLogger` event.
2. **Client hooks:** Port the ergonomics of `useAgentGraphData` (time-window calculation, graph availability heuristics) to Stageflow’s dashboard UI.
3. **Dashboard packaging:** Publish the dashboard as `stageflow-observability` optional component so existing deployments can opt in.

### Phase 4 – Advanced Features (post-MVP)

1. **Real-time alerts:** Integrate queue metrics into Prometheus/Grafana, similar to Langfuse’s `recordDistribution`/`recordIncrement` inside instrumentation.
2. **Session/user drilldowns:** Reproduce Langfuse’s user metrics queries to give product teams insight into top users, failure counts, and model spend.
3. **Replay hooks:** Enable “re-run pipeline from trace” by storing enough snapshot data alongside the events.

## 6. Stageflow Observability Dashboard Concept

| View | Data Source | Description |
| --- | --- | --- |
| Agent Graph | Repository query (Phase 2) | DAG visualization of stages/tools, adopting Langfuse node/step heuristics. |
| Pipeline Timeline | `WideEventEmitter` payloads | Timeline of stage durations, retries, and statuses. |
| Tool & Provider Metrics | `ProviderCallLogger` events + new ingestion store | Latency histograms, error rates, cost summaries by provider/model. |
| User/Org Insights | Future metrics queries | Aggregations per `ctx.user_id` / `ctx.org_id`, referencing Langfuse’s user metrics query. |

## 7. Immediate Next Steps

1. **Design the telemetry schema** and data contracts (Phase 0) to ensure backward compatibility.
2. **Prototype ingestion worker** using Stageflow’s event sink feeding a local ClickHouse instance.
3. **Draft API + dashboard skeleton** to validate data shape (even with synthetic data) before full storage build-out.

## 8. Open Questions

1. **Storage choice:** Reuse Langfuse’s ClickHouse/S3 combo or pick a simpler Postgres-first path?
2. **Self-hosting footprint:** Should the dashboard run as part of Stageflow or as an optional sidecar service?
3. **Sampling policy:** Do we expose user-configurable sampling similar to Langfuse’s `isTraceIdInSample`, or rely on OTEL sampling upstream?
