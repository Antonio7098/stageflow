# Composing Pipelines

Pipelines are the backbone of stageflow applications. This guide covers how to build, compose, and manage pipelines effectively.

## The Pipeline Builder

The `Pipeline` class provides a fluent API for building stage DAGs:

```python
from stageflow import Pipeline, StageKind

pipeline = (
    Pipeline()
    .with_stage("stage_a", StageA, StageKind.TRANSFORM)
    .with_stage("stage_b", StageB, StageKind.ENRICH)
    .with_stage("stage_c", StageC, StageKind.TRANSFORM, dependencies=("stage_a", "stage_b"))
)
```

## Adding Stages

### Basic Stage Addition

```python
pipeline.with_stage(
    name="my_stage",           # Unique name within pipeline
    runner=MyStage,            # Stage class, instance, or async callable
    kind=StageKind.TRANSFORM,  # Stage categorization
)
```

Plain async callable runners are supported when a dedicated stage class would be
unnecessary:

```python
async def echo_stage(ctx: StageContext) -> StageOutput:
    return StageOutput.ok(data={"echo": ctx.snapshot.input_text})

pipeline = Pipeline().with_stage("echo", echo_stage, StageKind.TRANSFORM)
```

### With Dependencies

Specify which stages must complete before this one runs:

```python
pipeline.with_stage(
    name="final",
    runner=FinalStage,
    kind=StageKind.TRANSFORM,
    dependencies=("stage_a", "stage_b", "stage_c"),  # Tuple of stage names
)
```

### Conditional Stages

Mark stages that may be skipped based on runtime conditions:

```python
pipeline.with_stage(
    name="optional_enrich",
    runner=OptionalEnrichStage,
    kind=StageKind.ENRICH,
    conditional=True,  # May be skipped
)
```

## Dependency Patterns

### Linear Chain

Stages run one after another:

```
[A] → [B] → [C]
```

```python
pipeline = (
    Pipeline()
    .with_stage("a", StageA, StageKind.TRANSFORM)
    .with_stage("b", StageB, StageKind.TRANSFORM, dependencies=("a",))
    .with_stage("c", StageC, StageKind.TRANSFORM, dependencies=("b",))
)
```

### Fan-Out (Parallel)

Multiple stages run concurrently from a single source:

```
        ┌→ [B]
[A] ────┼→ [C]
        └→ [D]
```

```python
pipeline = (
    Pipeline()
    .with_stage("a", StageA, StageKind.TRANSFORM)
    .with_stage("b", StageB, StageKind.ENRICH, dependencies=("a",))
    .with_stage("c", StageC, StageKind.ENRICH, dependencies=("a",))
    .with_stage("d", StageD, StageKind.ENRICH, dependencies=("a",))
)
```

### Fan-In (Aggregation)

Multiple stages feed into a single stage:

```
[A] ──┐
[B] ──┼→ [D]
[C] ──┘
```

```python
pipeline = (
    Pipeline()
    .with_stage("a", StageA, StageKind.ENRICH)
    .with_stage("b", StageB, StageKind.ENRICH)
    .with_stage("c", StageC, StageKind.ENRICH)
    .with_stage("d", StageD, StageKind.TRANSFORM, dependencies=("a", "b", "c"))
)
```

### Diamond Pattern

Fan-out followed by fan-in:

```
        ┌→ [B] ─┐
[A] ────┤       ├→ [D]
        └→ [C] ─┘
```

```python
pipeline = (
    Pipeline()
    .with_stage("a", StageA, StageKind.TRANSFORM)
    .with_stage("b", StageB, StageKind.ENRICH, dependencies=("a",))
    .with_stage("c", StageC, StageKind.ENRICH, dependencies=("a",))
    .with_stage("d", StageD, StageKind.TRANSFORM, dependencies=("b", "c"))
)
```

### Duplex Pattern (Bidirectional Systems)

Use duplex topology helpers when you need two directional lanes (A -> B and B -> A)
plus an optional synchronization stage.

```
[ingress_a] -> [uplink_decode] -> [uplink_apply] --\
                                                    -> [state_sync]
[ingress_b] -> [downlink_decode] -> [downlink_apply] -/
```

```python
from stageflow.pipeline import (
    DuplexLaneSpec,
    DuplexSystemSpec,
    PipelineBuilder,
    with_duplex_system,
)

# `with_duplex_system(...)` currently targets the deprecated PipelineBuilder API.
builder = (
    PipelineBuilder("duplex_chat")
    .with_stage("ingress_a", IngressAStage())
    .with_stage("ingress_b", IngressBStage())
)

system = DuplexSystemSpec(
    forward=DuplexLaneSpec(
        stages=(
            ("uplink_decode", UplinkDecodeStage()),
            ("uplink_apply", UplinkApplyStage()),
        ),
        depends_on=("ingress_a",),
    ),
    reverse=DuplexLaneSpec(
        stages=(
            ("downlink_decode", DownlinkDecodeStage()),
            ("downlink_apply", DownlinkApplyStage()),
        ),
        depends_on=("ingress_b",),
    ),
    join_stage=("state_sync", StateSyncStage()),
)

pipeline = with_duplex_system(builder, system)
```

#### Fluent Duplex Example

For concise topology creation:

```python
from stageflow.pipeline import FluentPipelineBuilder

pipeline = (
    FluentPipelineBuilder("duplex_realtime")
    .stage("ingress", IngressStage())
    .duplex(
        forward=(
            ("uplink_parse", UplinkParseStage()),
            ("uplink_send", UplinkSendStage()),
        ),
        reverse=(
            ("downlink_parse", DownlinkParseStage()),
            ("downlink_send", DownlinkSendStage()),
        ),
        join_stage=("sync_metrics", SyncMetricsStage()),
    )
    .build()
)
```

If `forward_depends_on` and `reverse_depends_on` are omitted, both lanes use
the previous fluent stage (`ingress` in this example) as their first dependency.

### Complex DAG

Real pipelines often combine multiple patterns:

```
[guard] ──→ [router] ──┐
                       │
[profile] ─────────────┼──→ [llm] ──→ [output_guard]
                       │
[memory] ──────────────┘
```

```python
pipeline = (
    Pipeline()
    # Input validation
    .with_stage("guard", InputGuardStage, StageKind.GUARD)
    # Routing (after guard)
    .with_stage("router", RouterStage, StageKind.ROUTE, dependencies=("guard",))
    # Parallel enrichment (no dependencies on each other)
    .with_stage("profile", ProfileEnrichStage, StageKind.ENRICH)
    .with_stage("memory", MemoryEnrichStage, StageKind.ENRICH)
    # LLM waits for routing and enrichment
    .with_stage(
        "llm",
        LLMStage,
        StageKind.TRANSFORM,
        dependencies=("router", "profile", "memory"),
    )
    # Output validation
    .with_stage("output_guard", OutputGuardStage, StageKind.GUARD, dependencies=("llm",))
    # Streaming telemetry stage (optional)
    .with_stage(
        "stream_monitor",
        StreamingTelemetryStage,
        StageKind.WORK,
        dependencies=("llm",),
    )
)
```

## Pipeline Composition

### Merging Pipelines

Combine two pipelines with `compose()`:

```python
# Base pipeline
base = (
    Pipeline()
    .with_stage("input", InputStage, StageKind.TRANSFORM)
    .with_stage("process", ProcessStage, StageKind.TRANSFORM, dependencies=("input",))
)

# Extension pipeline
extension = (
    Pipeline()
    .with_stage("enrich", EnrichStage, StageKind.ENRICH)
    .with_stage("output", OutputStage, StageKind.TRANSFORM, dependencies=("process", "enrich"))
)

# Merged pipeline has all stages
full_pipeline = base.compose(extension)
```

### Stage Name Conflicts

When composing, if stage names conflict, the second pipeline's stage wins:

```python
pipeline_a = Pipeline().with_stage("shared", StageA, StageKind.TRANSFORM)
pipeline_b = Pipeline().with_stage("shared", StageB, StageKind.TRANSFORM)

merged = pipeline_a.compose(pipeline_b)
# "shared" stage is now StageB
```

### Building Reusable Components

Create factory functions for common patterns:

```python
def create_enrichment_pipeline() -> Pipeline:
    """Reusable enrichment stages."""
    return (
        Pipeline()
        .with_stage("profile", ProfileEnrichStage(), StageKind.ENRICH)
        .with_stage("memory", MemoryEnrichStage(), StageKind.ENRICH)
        .with_stage("documents", DocumentEnrichStage(), StageKind.ENRICH)
    )

def create_guard_pipeline() -> Pipeline:
    """Reusable guard stages."""
    return (
        Pipeline()
        .with_stage("input_guard", InputGuardStage(), StageKind.GUARD)
        .with_stage("output_guard", OutputGuardStage(), StageKind.GUARD)
    )

# Compose into full pipeline
def create_chat_pipeline() -> Pipeline:
    return (
        create_guard_pipeline()
        .compose(create_enrichment_pipeline())
        .with_stage(
            "llm",
            LLMStage(),
            StageKind.TRANSFORM,
            dependencies=("input_guard", "profile", "memory"),
        )
        .with_stage(
            "analytics_exporter",
            AnalyticsStage(on_overflow_alert=my_alert_fn),
            StageKind.WORK,
            dependencies=("llm",),
        )
    )
```

## Building and Running

### Build the Graph

Convert the pipeline to an executable `UnifiedStageGraph`:

```python
graph = pipeline.build()
```

This validates:
- At least one stage exists
- All dependencies reference existing stages
- No circular dependencies

### Run the Graph

Execute with a `PipelineContext`:

```python
from stageflow import PipelineContext
from stageflow.helpers import ChunkQueue

pipeline_ctx = PipelineContext(
    input_text="Hello",
    topology="pipeline",
    execution_mode="practice",
)

results = await pipeline.run(pipeline_ctx)

# Emit basic streaming telemetry while running
queue = ChunkQueue(event_emitter=pipeline_ctx.try_emit_event)
await queue.put("warmup")
await queue.close()
```

### Access Results

Results are a dict mapping stage name to `StageOutput`:

```python
results = await pipeline.run(pipeline_ctx)

# Access specific stage output
llm_output = results["llm"]
print(llm_output.status)  # StageStatus.OK
print(llm_output.data)    # {"response": "Hello!"}

# Check all stages
for name, output in results.items():
    print(f"{name}: {output.status.value}")
```

## Pipeline Registry

For applications with multiple pipelines, use the registry:

```python
from stageflow import pipeline_registry

# Register pipelines
pipeline_registry.register("chat_fast", create_chat_fast_pipeline())
pipeline_registry.register("chat_accurate", create_chat_accurate_pipeline())
pipeline_registry.register("voice", create_voice_pipeline())

# Retrieve by name
pipeline = pipeline_registry.get("chat_fast")
graph = pipeline.build()

# List all registered
names = pipeline_registry.list()  # ["chat_fast", "chat_accurate", "voice"]
```

## Passing Configuration

### Stage-Level Configuration

Pass configuration when building the context:

```python
pipeline_ctx = PipelineContext(
    ...,
    metadata={"timeout": 30000, "model": "gpt-4"},
)
```

### Per-Stage Configuration

Use stage initialization for stage-specific config:

```python
pipeline = (
    Pipeline()
    .with_stage("llm_fast", LLMStage(model="gpt-3.5-turbo"), StageKind.TRANSFORM)
    .with_stage("llm_accurate", LLMStage(model="gpt-4"), StageKind.TRANSFORM)
)
```

## Error Handling

### Stage Failures

When a stage fails, the pipeline stops and raises `StageExecutionError`:

```python
from stageflow import StageExecutionError

try:
    results = await pipeline.run(pipeline_ctx)
except StageExecutionError as e:
    print(f"Stage '{e.stage}' failed: {e.original}")
```

### Pipeline Cancellation

When a stage returns `StageOutput.cancel()`, the pipeline stops gracefully:

```python
from stageflow.pipeline.dag import UnifiedPipelineCancelled

try:
    results = await pipeline.run(pipeline_ctx)
except UnifiedPipelineCancelled as e:
    print(f"Pipeline cancelled by '{e.stage}': {e.reason}")
    # Access partial results
    partial_results = e.results
```

## Best Practices

### 1. Name Stages Descriptively

Use clear, descriptive names:

```python
# Good
.with_stage("validate_input", ...)
.with_stage("enrich_user_profile", ...)
.with_stage("generate_response", ...)

# Bad
.with_stage("stage1", ...)
.with_stage("s2", ...)
.with_stage("x", ...)
```

### 2. Minimize Dependencies

Only add dependencies that are truly required:

```python
# Good: Only depends on what it needs
.with_stage("llm", LLMStage, dependencies=("router", "profile"))

# Bad: Unnecessary dependencies slow execution
.with_stage("llm", LLMStage, dependencies=("router", "profile", "memory", "guard", "logger"))
```

### 3. Use Factory Functions

Create pipelines via factory functions for testability:

```python
def create_pipeline(llm_client=None, profile_service=None) -> Pipeline:
    """Create pipeline with injectable dependencies."""
    return (
        Pipeline()
        .with_stage("profile", ProfileEnrichStage(profile_service), StageKind.ENRICH)
        .with_stage("llm", LLMStage(llm_client), StageKind.TRANSFORM, dependencies=("profile",))
    )

# Production
pipeline = create_pipeline(llm_client=real_client, profile_service=real_service)

# Testing
pipeline = create_pipeline(llm_client=mock_client, profile_service=mock_service)
```

### 4. Document Your DAGs

Add comments showing the DAG structure:

```python
def create_full_pipeline() -> Pipeline:
    """Create the full chat pipeline.
    
    DAG:
        [input_guard] → [router] ─┐
                                  │
        [profile] ────────────────┼→ [llm] → [output_guard]
                                  │
        [memory] ─────────────────┘
    """
    return (
        Pipeline()
        # ... stages
    )
```

## Next Steps

- [Context & Data Flow](context.md) — How data moves between stages
- [Interceptors](interceptors.md) — Add middleware to your pipelines
- [Examples](../examples/full.md) — See complete pipeline examples
