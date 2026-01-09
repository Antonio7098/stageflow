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
from stageflow import StageContext, StageKind, StageOutput


class EchoStage:
    """Simple stage that echoes the input text."""

    name = "echo"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Simulate some processing time
        await asyncio.sleep(0.2)

        # Get input from context
        inputs = ctx.config.get("inputs")
        if inputs:
            input_text = inputs.snapshot.input_text or ""
        else:
            input_text = ctx.snapshot.input_text or ""

        # Return the echoed text
        return StageOutput.ok(
            echo=input_text,
            message=f"Echoed: {input_text}",
        )
```

### Key Points

1. **Stage Protocol**: The class has `name`, `kind`, and `execute()` method
2. **Async Execution**: The `execute` method is async
3. **Input Access**: Input comes from `ctx.snapshot.input_text`
4. **Output**: Returns `StageOutput.ok()` with data

## The Pipeline

```python
from stageflow import Pipeline, StageKind


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
from uuid import uuid4

from stageflow import Pipeline, StageContext, StageKind, StageOutput
from stageflow.context import ContextSnapshot


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
    
    # Build the executable graph
    graph = pipeline.build()
    
    # Create the context with input
    snapshot = ContextSnapshot(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=None,
        interaction_id=uuid4(),
        topology="simple",
        execution_mode="default",
        input_text="Hello, Stageflow!",
    )
    
    ctx = StageContext(snapshot=snapshot)
    
    # Run the pipeline
    results = await graph.run(ctx)
    
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
2. **Graph Building**: `pipeline.build()` creates an executable `StageGraph`
3. **Context Creation**: We create a `ContextSnapshot` with our input
4. **Execution**: `graph.run(ctx)` executes all stages
5. **Results**: We get a dict mapping stage names to `StageOutput`

## Variations

### With Configuration

```python
ctx = StageContext(
    snapshot=snapshot,
    config={
        "timeout": 5000,  # 5 second timeout
        "custom_setting": "value",
    },
)
```

### With Event Sink

```python
from stageflow import set_event_sink, LoggingEventSink

# Enable event logging
set_event_sink(LoggingEventSink())

# Now all stage events will be logged
results = await graph.run(ctx)
```

### Error Handling

```python
from stageflow.pipeline.dag import StageExecutionError

try:
    results = await graph.run(ctx)
except StageExecutionError as e:
    print(f"Stage '{e.stage}' failed: {e.original}")
```

## Next Steps

- [Transform Chain](transform-chain.md) — Multiple stages in sequence
- [Parallel Enrichment](parallel.md) — Stages running concurrently
- [Building Stages](../guides/stages.md) — Deep dive into stage creation
