# Simple Pipeline Example

This example demonstrates the most basic stageflow pipeline: a single stage that echoes input.

## Overview

```
[echo]
```

A single TRANSFORM stage that receives input and returns it unchanged.

## The Stage

```python
import asyncio
from stageflow.api import StageContext, StageKind, StageOutput


class EchoStage:
    """Simple stage that echoes the input text."""

    name = "echo"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Simulate some processing time
        await asyncio.sleep(0.2)

        # Get input from context
        input_text = ctx.snapshot.input_text or ""

        # Wrap echoed text with standardized LLM metadata for observability
        from stageflow.helpers import LLMResponse

        llm = LLMResponse(
            content=input_text,
            model="echo-simulator",
            provider="demo",
            input_tokens=len(input_text),
            output_tokens=len(input_text),
        )

        # Return the echoed text
        return StageOutput.ok(
            echo=llm.content,
            message=f"Echoed: {llm.content}",
            llm=llm.to_dict(),
        )
```

### Key Points

1. **Stage Protocol**: The class has `name`, `kind`, and `execute()` method
2. **Async Execution**: The `execute` method is async
3. **Input Access**: Input comes from `ctx.snapshot.input_text`
4. **Output**: Returns `StageOutput.ok()` with data

## The Pipeline

```python
from stageflow.api import Pipeline, StageKind


def create_simple_pipeline() -> Pipeline:
    """Create a simple single-stage pipeline.
    
    DAG:
        [echo]
    """
    return Pipeline().with_stage(
        name="echo",
        runner=EchoStage,
        kind=StageKind.TRANSFORM,
    )
```

### Key Points

1. **Pipeline Builder**: Use `Pipeline()` with fluent `.with_stage()` calls
2. **Stage Registration**: Pass name, runner class, and kind
3. **No Dependencies**: Single stage has no dependencies

## Running the Pipeline

```python
import asyncio

from stageflow.api import Pipeline, PipelineContext, StageContext, StageKind, StageOutput


class EchoStage:
    name = "echo"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        input_text = ctx.snapshot.input_text or ""
        return StageOutput.ok(
            echo=input_text,
            message=f"Echoed: {input_text}",
        )


async def main():
    # Create the pipeline
    pipeline = Pipeline().with_stage("echo", EchoStage, StageKind.TRANSFORM)
    
    # Create the pipeline entry context
    pipeline_ctx = PipelineContext(
        topology="simple",
        execution_mode="default",
        input_text="Hello, Stageflow!",
    )
    
    # Run the pipeline
    results = await pipeline.run(pipeline_ctx)
    
    # Access results
    echo_output = results["echo"]
    print(f"Status: {echo_output.status.value}")
    print(f"Echo: {echo_output.data['echo']}")
    print(f"Message: {echo_output.data['message']}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Output

```
Status: ok
Echo: Hello, Stageflow!
Message: Echoed: Hello, Stageflow!
```

## What's Happening

1. **Pipeline Creation**: We create a pipeline with one stage
2. **Context Creation**: We create a `PipelineContext` with our input
3. **Execution**: `pipeline.run(pipeline_ctx)` builds and executes the graph
4. **Results**: We get a dict mapping stage names to `StageOutput`

## Variations

### With Configuration

```python
# Attach custom settings to PipelineContext metadata for stage access.
pipeline_ctx = PipelineContext(
    metadata={
        "timeout_ms": 5000,
        "custom_setting": "value",
    },
)
```

### With Event Sink & Streaming Telemetry

```python
from stageflow import set_event_sink, LoggingEventSink
from stageflow.helpers import ChunkQueue

# Enable event logging
set_event_sink(LoggingEventSink())

# Now all stage events will be logged
results = await pipeline.run(pipeline_ctx)

# Emit queue telemetry even in simple pipelines (tracks drops/throttle)
queue = ChunkQueue(event_emitter=lambda event, attrs: print(event, attrs))
await queue.put("warmup")
await queue.close()
```

### Error Handling

```python
from stageflow import UnifiedStageExecutionError

try:
    results = await pipeline.run(pipeline_ctx)
except UnifiedStageExecutionError as e:
    print(f"Stage '{e.stage}' failed: {e.original}")
```

## Next Steps

- [Transform Chain](transform-chain.md) — Multiple stages in sequence
- [Parallel Enrichment](parallel.md) — Stages running concurrently
- [Building Stages](../guides/stages.md) — Deep dive into stage creation
