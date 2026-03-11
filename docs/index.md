# Stageflow Documentation

**Stageflow** is a Python framework for building observable, composable pipeline architectures with parallel execution, cancellation support, and middleware interceptors.

## What is Stageflow?

Stageflow provides a **DAG-based execution substrate** for building complex data processing and AI agent pipelines. It separates the concerns of *orchestration* (how stages run) from *business logic* (what stages do), enabling you to build maintainable, testable, and observable systems.

```python
from stageflow.api import Pipeline, StageContext, StageKind, stage_metadata

@stage_metadata(name="greet", kind=StageKind.TRANSFORM)
class GreetStage:
    async def execute(self, ctx: StageContext) -> dict[str, str]:
        name = ctx.snapshot.input_text or "World"
        return {"message": f"Hello, {name}!"}

# Build and run the pipeline
pipeline = Pipeline().with_stage("greet", GreetStage)
results = await pipeline.run(input_text="Stageflow")
```

## Key Features

- **DAG-Based Execution** — Stages run as soon as their dependencies resolve, enabling maximum parallelism
- **Type-Safe Pipelines** — Define pipelines in Python code with full IDE support and compile-time safety
- **Composable Architecture** — Combine pipelines, share stages, and build complex workflows from simple parts
- **Built-in Observability** — Structured logging, streaming telemetry events, analytics buffering with overflow callbacks, and distributed tracing out of the box
- **Interceptor Middleware** — Add cross-cutting concerns (auth, timeouts, circuit breakers) without modifying stages
- **Cancellation Support** — Graceful pipeline cancellation with structured cleanup and resource management
- **Multi-Tenant Isolation** — Built-in tenant validation, isolation tracking, and tenant-aware logging
- **Event Backpressure** — Bounded event queues with backpressure handling to prevent memory exhaustion
- **Tool Execution System** — First-class support for agent tools with undo, approval, and behavior gating

## Documentation Structure

The docs are organized into the following sections:

- [Getting Started](getting-started/) - installation, quickstart, concepts
- [Guides](guides/) - stages, pipelines, dependencies, governance, observability, release workflow, tools, approval
- [Examples](examples/) - simple pipeline, transform chain, parallel enrichment, chat pipeline, full pipeline, agent with tools
- [API Reference](api/) - core types, pipeline, context, interceptors, events, protocols, observability, extensions
- [Advanced Topics](advanced/) - pipeline composition, subpipeline runs, custom interceptors, error handling, testing strategies, extensions

> **New in Stageflow 1.1.0**

> - **Reusable Agent Runtime**: Added `stageflow.agent.Agent` and `AgentStage` for prompt-driven tool loops with typed turn contracts and stage-friendly integration.
> - **Prompt Safety & Validation**: Added versioned prompt templates, prompt-injection hardening, and Pydantic-backed structured-output retries for more reliable LLM execution.
> - **OpenRouter Response Robustness**: Normalization now handles nested OpenAI/OpenRouter envelopes, null/list content variants, and tool-call extraction across real provider response shapes.

> **New in Stageflow 0.9.5**
>
> - **Duplex Pipeline Systems**: Added `DuplexLaneSpec`, `DuplexSystemSpec`, `with_duplex_system()` helper, and `FluentPipelineBuilder.duplex()` for low-boilerplate bidirectional pipeline construction (A→B and B→A lanes with optional sync stage).
> - **Expanded Builder Helpers**: Fluent builder now supports duplex topologies alongside linear chains, parallel stages, and fan-out/fan-in patterns.
> - **Documentation**: New duplex-systems guide covering structured and fluent builder usage, dependency behavior, validation, and testing patterns.

> **New in Stageflow 0.9.3**
>
> - **Tier 2 Report Remediation**: Governance, authentication, and context guides now reflect current organizational risk controls, canonical GitHub URLs, and consistent tooling workflows.
> - **Tools, Approvals & Pipelines**: Approval service enums, pipeline interceptors, and port helpers were reorganized to stay compatible with the latest lint rules and runtime signatures.
> - **Documentation Refresh**: Tools, tools-approval, stage, and voice guides have been trimmed and rephrased so the published docs align with the running Stageflow release.
> - **Context & Stageflow Helpers**: StageInputs, stage ports, and interceptors received small tweaks so import order and helper exports cleanly match the canonical `Antonio7098/stageflow` codebase.

## Links

- [GitHub Repository](https://github.com/yourorg/stageflow)
- [Issue Tracker](https://github.com/yourorg/stageflow/issues)
- [**Composing Pipelines**](guides/pipelines.md) — Build complex DAGs from simple stages
- [**Duplex Systems**](guides/duplex-systems.md) — Build bidirectional A->B / B->A pipeline topologies
- [**Context & Data Flow**](guides/context.md) — Pass data between stages
- [**Interceptors**](guides/interceptors.md) — Add middleware for cross-cutting concerns
- [**Tools & Agents**](guides/tools.md) — Build agent capabilities with tools and parse LLM tool calls safely
- [**Agent Runtime & Prompt Safety**](guides/agents.md) — Version prompts, harden prompts against injection, validate outputs, and run tool loops
- [**Real-Time Streaming**](guides/realtime-streaming.md) — Stream chunks directly between running stages (LLM -> TTS)
- [**Observability**](guides/observability.md) — Monitor and debug your pipelines with telemetry streams and analytics exporters

## Getting Started
- **Happy-path imports**: if you want the smallest practical public surface, start with `from stageflow.api import ...`.
- [**Installation**](getting-started/installation.md) — Install stageflow and set up your environment
- [**Quick Start**](getting-started/quickstart.md) — Build your first pipeline in 5 minutes
- [**Core Concepts**](getting-started/concepts.md) — Understand the fundamental ideas

### Guides
- [**Building Stages**](guides/stages.md) — Create custom stages for your pipelines
- [**Composing Pipelines**](guides/pipelines.md) — Build complex DAGs from simple stages
- [**Duplex Systems**](guides/duplex-systems.md) — Dedicated guide for bidirectional lane construction and sync stages
- [**Dependency Declaration**](guides/dependencies.md) — Declare and manage stage dependencies
- [**Context & Data Flow**](guides/context.md) — Pass data between stages
- [**Interceptors**](guides/interceptors.md) — Add middleware for cross-cutting concerns
- [**Tools & Agents**](guides/tools.md) — Build agent capabilities with tools and parse LLM tool calls safely
- [**Agent Runtime & Prompt Safety**](guides/agents.md) — Reusable agent runtime with versioned prompts, security, retries, and tool loops
- [**Real-Time Streaming**](guides/realtime-streaming.md) — Stage-to-stage streaming patterns using RealtimeStageBus
- [**Tools & Approval Workflows**](guides/tools-approval.md) — Implement HITL approval flows for tools
- [**Observability**](guides/observability.md) — Monitor and debug your pipelines with telemetry streams and analytics exporters
- [**Authentication**](guides/authentication.md) — Secure your pipelines with auth interceptors
- [**Governance & Security**](guides/governance.md) — Multi-tenant isolation, guardrails, and audit patterns
- [**Voice & Audio**](guides/voice-audio.md) — Build voice pipelines with STT/TTS and streaming
- [**Releasing**](guides/releasing.md) — Step-by-step instructions for cutting a new Stageflow release

### Examples
- [**Simple Pipeline**](examples/simple.md) — Single-stage echo pipeline
- [**Transform Chain**](examples/transform-chain.md) — Sequential data transformations
- [**Parallel Enrichment**](examples/parallel.md) — Fan-out/fan-in patterns
- [**Real-Time LLM->TTS Streaming**](examples/realtime-llm-tts.md) — Concurrent stage-to-stage chunk handoff with RealtimeStageBus
- [**Chat Pipeline**](examples/chat.md) — LLM-powered conversational pipeline
- [**Full Pipeline**](examples/full.md) — Complete pipeline with all features
- [**Agent with Tools**](examples/agent-tools.md) — Agent stage with tool execution

### API Reference
- [**Core Types**](api/core.md) — Stage, StageOutput, StageContext, StageKind
- [**Pipeline**](api/pipeline.md) — Pipeline builder, UnifiedStageGraph (default), and StageGraph (deprecated compatibility)
- [**Advanced API Surface**](api/advanced.md) — `stageflow.advanced` imports for runtime customization and internals
- [**Context**](api/context.md) — PipelineContext, ContextSnapshot, StageInputs
- [**StageInputs**](api/inputs.md) — Immutable access to prior stage outputs with validation
- [**Context Sub-modules**](api/context-submodules.md) — OutputBag, Conversation, Enrichments, Extensions
- [**Interceptors**](api/interceptors.md) — BaseInterceptor and built-in interceptors
- [**Tools**](api/tools.md) — Tool definitions, registry, and executor
- [**Events**](api/events.md) — EventSink and event types
- [**Protocols**](api/protocols.md) — ExecutionContext, RunStore, ConfigProvider, CorrelationIds
- [**Observability**](api/observability.md) — Logging protocols and utilities
- [**Wide Events**](api/wide-events.md) — Pipeline-level and stage-level event emission
- [**Auth**](api/auth.md) — AuthContext, OrgContext, and auth interceptors
- [**Helper Modules**](api/helpers.md) — Memory, Guardrails, Streaming, Analytics, Mocks
- [**CLI**](api/cli.md) — Dependency linting and pipeline validation tools
- [**Projector**](api/projector.md) — WebSocket projection services
- [**Testing**](api/testing.md) — Testing utilities and helpers

### Advanced Topics
- [**Pipeline Composition**](advanced/composition.md) — Merging and extending pipelines
- [**Subpipeline Runs**](advanced/subpipelines.md) — Nested pipeline execution
- [**Custom Interceptors**](advanced/custom-interceptors.md) — Build your own middleware
- [**Idempotency Patterns**](advanced/idempotency.md) — Enforce duplicate suppression for WORK stages
- [**Error Handling**](advanced/errors.md) — Error taxonomy and recovery strategies
- [**Testing Strategies**](advanced/testing.md) — Unit, integration, and contract testing
- [**Extensions**](advanced/extensions.md) — Add application-specific data to contexts

## Root Exports Index

The following symbols are exported from `stageflow` and can be imported directly:

| Symbol | Category | Documentation |
|--------|----------|---------------|
| `Stage`, `StageKind`, `StageStatus`, `StageOutput` | Core | [Core Types](api/core.md) |
| `StageContext`, `StageArtifact`, `StageEvent` | Core | [Core Types](api/core.md) |
| `PipelineTimer`, `create_stage_context` | Core | [Core Types](api/core.md) |
| `Pipeline`, `UnifiedStageSpec` | Pipeline | [Pipeline](api/pipeline.md) |
| `UnifiedStageGraph`, `UnifiedStageSpec` | Pipeline | [Pipeline](api/pipeline.md) |
| `StageGraph`, `StageSpec`, `StageExecutionError` | Pipeline (Deprecated) | [Pipeline](api/pipeline.md) |
| `PipelineRegistry`, `pipeline_registry` | Pipeline | [Pipeline](api/pipeline.md) |
| `PipelineContext`, `StageResult`, `StageError` | Context | [Context](api/context.md) |
| `extract_service` | Context | [Context](api/context.md) |
| `BaseInterceptor`, `InterceptorResult`, `InterceptorContext` | Interceptors | [Interceptors](api/interceptors.md) |
| `ErrorAction`, `get_default_interceptors`, `run_with_interceptors` | Interceptors | [Interceptors](api/interceptors.md) |
| `TimeoutInterceptor`, `CircuitBreakerInterceptor` | Interceptors | [Interceptors](api/interceptors.md) |
| `LoggingInterceptor`, `MetricsInterceptor`, `ChildTrackerMetricsInterceptor`, `TracingInterceptor` | Interceptors | [Interceptors](api/interceptors.md) |
| `EventSink`, `NoOpEventSink`, `LoggingEventSink` | Events | [Events](api/events.md) |
| `get_event_sink`, `set_event_sink`, `clear_event_sink` | Events | [Events](api/events.md) |
| `RunStore`, `ConfigProvider`, `CorrelationIds` | Protocols | [Protocols](api/protocols.md) |
| `CircuitBreaker`, `CircuitBreakerOpenError` | Observability | [Observability](api/observability.md) |
| `PipelineRunLogger`, `ProviderCallLogger` | Observability | [Observability](api/observability.md) |
| `summarize_pipeline_error`, `get_circuit_breaker` | Observability | [Observability](api/observability.md) |
| `ExtensionRegistry`, `ExtensionHelper`, `TypedExtension` | Extensions | [Extensions](advanced/extensions.md) |

**Context module** (`from stageflow.context import ...`):

| Symbol | Documentation |
|--------|---------------|
| `PipelineContext`, `ContextSnapshot`, `RunIdentity` | [Context](api/context.md) |
| `Message`, `RoutingDecision` | [Context](api/context.md) |
| `ProfileEnrichment`, `MemoryEnrichment`, `DocumentEnrichment` | [Context](api/context.md) |

**API module** (`from stageflow.api import ...`):

| Symbol | Documentation |
|--------|---------------|
| `StageInputs`, `create_stage_inputs` | [Context](api/context.md#stageinputs) |
| `CorePorts`, `LLMPorts`, `AudioPorts` | [Context](api/context-submodules.md) |

**Advanced module** (`from stageflow.advanced import ...`):

| Symbol | Documentation |
|--------|---------------|
| `SubpipelineSpawner`, `SubpipelineResult` | [Subpipelines](advanced/subpipelines.md) |
| `ChildRunTracker`, `get_child_tracker` | [Subpipelines](advanced/subpipelines.md) |
| `PipelineSpawnedChildEvent`, `PipelineChildCompletedEvent` | [Subpipelines](advanced/subpipelines.md) |
| `PipelineChildFailedEvent`, `PipelineCanceledEvent` | [Subpipelines](advanced/subpipelines.md) |

## Philosophy

Stageflow is built on several core principles:

1. **Containers vs. Payloads** — Stages own orchestration (timeouts, retries, telemetry). Business logic lives in the payloads (agents, tools, enrichers).

2. **Separation of Concerns** — Topology (DAG structure), Configuration (provider/model wiring), and Behavior (runtime hints) are kept separate.

3. **Observability is Reality** — If it's not logged, traced, and replayable, it didn't happen.

4. **Parallel by Default** — Stages run as soon as dependencies resolve. The framework handles concurrency.

5. **Immutable Data Flow** — Context snapshots are frozen. Stages read inputs and produce outputs without side effects on shared state.

## Requirements

- Python 3.11+
- asyncio-based runtime

## License

MIT License
