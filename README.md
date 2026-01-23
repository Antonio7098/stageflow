# Stageflow

A DAG-based pipeline orchestration framework for building observable, composable stage pipelines in Python.

## Features

- **DAG Execution**: Stages execute as soon as dependencies resolve, maximizing parallelism
- **Fluent Pipeline Builder**: Type-safe, composable pipeline definitions
- **Interceptor Framework**: Middleware pattern for cross-cutting concerns (timeouts, circuit breakers, tracing, metrics)
- **Observable by Design**: Structured events, correlation IDs, and logging built-in
- **Protocol-Based Extension**: Clean abstractions for persistence, configuration, and events
- **Async-First**: Built on asyncio for high-performance concurrent execution
- **Zero Dependencies**: Core library has no external dependencies

## Installation

Latest release: v0.9.1

```bash
pip install stageflow-core
```

For development:
```bash
pip install stageflow-core[dev]
```

## Quick Start

```python
import asyncio
from stageflow import (
    Pipeline,
    Stage,
    StageContext,
    StageOutput,
    StageKind,
    PipelineTimer,
)
from stageflow.context import ContextSnapshot, RunIdentity
from stageflow.stages import StageInputs

# Define a stage
class GreetStage:
    name = "greet"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        name = ctx.snapshot.input_text or "World"
        return StageOutput.ok(greeting=f"Hello, {name}!")

# Define another stage that depends on the first
class ShoutStage:
    name = "shout"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Access output from dependency via StageInputs
        greeting = ctx.inputs.get_from("greet", "greeting", default="Hello!")
        return StageOutput.ok(shouted=greeting.upper())

# Build the pipeline
pipeline = (
    Pipeline()
    .with_stage("greet", GreetStage, StageKind.TRANSFORM)
    .with_stage("shout", ShoutStage, StageKind.TRANSFORM, dependencies=("greet",))
)

# Execute
async def main():
    graph = pipeline.build()
    snapshot = ContextSnapshot(run_id=RunIdentity(), input_text="World")
    base_inputs = StageInputs(snapshot=snapshot)
    ctx = StageContext(
        snapshot=snapshot,
        inputs=base_inputs,
        stage_name="pipeline_entry",
        timer=PipelineTimer(),
    )
    results = await graph.run(ctx)
    print(results["shout"].data["shouted"])  # "HELLO, WORLD!"

asyncio.run(main())
```

## Core Concepts

### Stages

A **Stage** is a unit of work with a defined input/output contract:

```python
class Stage(Protocol):
    name: str
    kind: StageKind

    async def execute(self, ctx: StageContext) -> StageOutput: ...
```

Stage kinds categorize behavior:
- `TRANSFORM` - Change input form (STT, TTS, LLM)
- `ENRICH` - Add context (profile, memory, skills)
- `ROUTE` - Select execution path
- `GUARD` - Validate (guardrails, policy)
- `WORK` - Side effects (persist, assess)
- `AGENT` - Main interaction logic

### Pipelines

**Pipelines** compose stages into a DAG using a fluent builder:

```python
pipeline = (
    Pipeline()
    .with_stage("stt", SttStage, StageKind.TRANSFORM)
    .with_stage("enrich", EnrichStage, StageKind.ENRICH, dependencies=("stt",))
    .with_stage("llm", LlmStage, StageKind.TRANSFORM, dependencies=("enrich",))
    .with_stage("tts", TtsStage, StageKind.TRANSFORM, dependencies=("llm",))
)
```

Pipelines can be composed:
```python
core_pipeline = Pipeline().with_stage(...)
voice_pipeline = core_pipeline.compose(
    Pipeline().with_stage("tts", TtsStage, StageKind.TRANSFORM, dependencies=("llm",))
)
```

### Interceptors

**Interceptors** wrap stage execution for cross-cutting concerns:

```python
from stageflow.interceptors import BaseInterceptor, InterceptorResult

class AuthInterceptor(BaseInterceptor):
    name = "auth"
    priority = 5  # Lower = runs first

    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        if not ctx.data.get("authenticated"):
            return InterceptorResult(stage_ran=False, error="Not authenticated")
        return None

    async def after(self, stage_name: str, result: StageResult, ctx: PipelineContext) -> None:
        pass
```

Built-in interceptors:
- `TimeoutInterceptor` - Per-stage timeouts
- `CircuitBreakerInterceptor` - Failure isolation
- `TracingInterceptor` - OpenTelemetry spans
- `MetricsInterceptor` - Stage duration/success metrics
- `LoggingInterceptor` - Structured JSON logging

### Event Sinks

**EventSink** is a protocol for event persistence:

```python
from stageflow import EventSink

class MyEventSink(EventSink):
    async def emit(self, *, type: str, data: dict | None) -> None:
        # Persist to your storage
        await db.insert("events", {"type": type, "data": data})

    def try_emit(self, *, type: str, data: dict | None) -> None:
        # Fire-and-forget variant
        asyncio.create_task(self.emit(type=type, data=data))
```

## Architecture

Stageflow follows **SOLID principles** with a clear separation:

```
┌─────────────────────────────────────────────────────────────┐
│                        Your Application                     │
├─────────────────────────────────────────────────────────────┤
│  Adapters (implement protocols)                             │
│  - DatabaseEventSink                                        │
│  - PostgresRunStore                                         │
│  - EnvConfigProvider                                        │
├─────────────────────────────────────────────────────────────┤
│                     stageflow (core)                        │
│  ┌─────────┐  ┌─────────┐  ┌─────────────┐  ┌─────────┐     │
│  │ Pipeline│  │  Graph  │  │ Interceptors│  │ Events  │     │
│  └─────────┘  └─────────┘  └─────────────┘  └─────────┘     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    Ports (protocols)                │    │
│  │  EventSink | RunStore | ConfigProvider              │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Event Taxonomy

Stageflow emits structured events for observability:

| Event Type | When |
|------------|------|
| `pipeline.created` | Pipeline run initialized |
| `pipeline.started` | Execution begins |
| `pipeline.completed` | All stages finished |
| `pipeline.failed` | Unrecoverable error |
| `pipeline.cancelled` | Graceful termination |
| `stage.{name}.started` | Stage execution begins |
| `stage.{name}.completed` | Stage finished successfully |
| `stage.{name}.failed` | Stage threw error |
| `stage.{name}.skipped` | Conditional stage skipped |

## License

MIT

## Contributing

Contributions welcome! Please read the contributing guide first.
