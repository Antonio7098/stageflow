# Stageflow Documentation

**Stageflow** is a Python framework for building observable, composable pipeline architectures with parallel execution, cancellation support, and middleware interceptors.

## What is Stageflow?

Stageflow provides a **DAG-based execution substrate** for building complex data processing and AI agent pipelines. It separates the concerns of *orchestration* (how stages run) from *business logic* (what stages do), enabling you to build maintainable, testable, and observable systems.

```python
from stageflow import Pipeline, StageKind, StageOutput

class GreetStage:
    name = "greet"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx):
        name = ctx.snapshot.input_text or "World"
        return StageOutput.ok(message=f"Hello, {name}!")

# Build and run the pipeline
pipeline = Pipeline().with_stage("greet", GreetStage, StageKind.TRANSFORM)
graph = pipeline.build()
results = await graph.run(ctx)
```

## Key Features

- **DAG-Based Execution** — Stages run as soon as their dependencies resolve, enabling maximum parallelism
- **Type-Safe Pipelines** — Define pipelines in Python code with full IDE support and compile-time safety
- **Composable Architecture** — Combine pipelines, share stages, and build complex workflows from simple parts
- **Built-in Observability** — Structured logging, metrics, tracing, and event emission out of the box
- **Interceptor Middleware** — Add cross-cutting concerns (auth, timeouts, circuit breakers) without modifying stages
- **Cancellation Support** — Graceful pipeline cancellation with proper cleanup
- **Tool Execution System** — First-class support for agent tools with undo, approval, and behavior gating

## Documentation Structure

### Getting Started
- [**Installation**](getting-started/installation.md) — Install stageflow and set up your environment
- [**Quick Start**](getting-started/quickstart.md) — Build your first pipeline in 5 minutes
- [**Core Concepts**](getting-started/concepts.md) — Understand the fundamental ideas

### Guides
- [**Building Stages**](guides/stages.md) — Create custom stages for your pipelines
- [**Composing Pipelines**](guides/pipelines.md) — Build complex DAGs from simple stages
- [**Context & Data Flow**](guides/context.md) — Pass data between stages
- [**Interceptors**](guides/interceptors.md) — Add middleware for cross-cutting concerns
- [**Tools & Agents**](guides/tools.md) — Build agent capabilities with tools
- [**Observability**](guides/observability.md) — Monitor and debug your pipelines
- [**Authentication**](guides/authentication.md) — Secure your pipelines with auth interceptors

### Examples
- [**Simple Pipeline**](examples/simple.md) — Single-stage echo pipeline
- [**Transform Chain**](examples/transform-chain.md) — Sequential data transformations
- [**Parallel Enrichment**](examples/parallel.md) — Fan-out/fan-in patterns
- [**Chat Pipeline**](examples/chat.md) — LLM-powered conversational pipeline
- [**Full Pipeline**](examples/full.md) — Complete pipeline with all features
- [**Agent with Tools**](examples/agent-tools.md) — Agent stage with tool execution

### API Reference
- [**Core Types**](api/core.md) — Stage, StageOutput, StageContext, StageKind
- [**Pipeline**](api/pipeline.md) — Pipeline builder and StageGraph
- [**Context**](api/context.md) — ContextSnapshot, ContextBag, enrichments
- [**Interceptors**](api/interceptors.md) — BaseInterceptor and built-in interceptors
- [**Tools**](api/tools.md) — Tool definitions, registry, and executor
- [**Events**](api/events.md) — EventSink and event types
- [**Observability**](api/observability.md) — Logging protocols and utilities
- [**Auth**](api/auth.md) — AuthContext, OrgContext, and auth interceptors

### Advanced Topics
- [**Pipeline Composition**](advanced/composition.md) — Merging and extending pipelines
- [**Subpipeline Runs**](advanced/subpipelines.md) — Nested pipeline execution
- [**Custom Interceptors**](advanced/custom-interceptors.md) — Build your own middleware
- [**Error Handling**](advanced/errors.md) — Error taxonomy and recovery strategies
- [**Testing Strategies**](advanced/testing.md) — Unit, integration, and contract testing
- [**Extensions**](advanced/extensions.md) — Add application-specific data to contexts

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
