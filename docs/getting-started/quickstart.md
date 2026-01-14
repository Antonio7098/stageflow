# Quick Start

This guide walks you through building your first stageflow pipeline in 5 minutes.

## Your First Pipeline

Let's build a simple pipeline that transforms user input through multiple stages.

### Step 1: Define Your Stages

Stages are the building blocks of pipelines. Each stage implements the `Stage` protocol:

```python
from stageflow import StageContext, StageKind, StageOutput

class UppercaseStage:
    """Transform text to uppercase."""
    
    name = "uppercase"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Get input from the context snapshot
        text = ctx.snapshot.input_text or ""
        
        # Transform and return
        result = text.upper()
        return StageOutput.ok(text=result)


class AddExclamationStage:
    """Add exclamation marks to text."""
    
    name = "exclaim"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        # Get output from previous stage via StageInputs
        text = ctx.inputs.get_from("uppercase", "text", default="")
        
        # Transform and return
        result = f"{text}!!!"
        return StageOutput.ok(text=result, excited=True)
```

### Step 2: Build the Pipeline

Use the `Pipeline` builder to compose stages into a DAG:

```python
from stageflow import Pipeline, StageKind

pipeline = (
    Pipeline()
    .with_stage(
        name="uppercase",
        runner=UppercaseStage,
        kind=StageKind.TRANSFORM,
    )
    .with_stage(
        name="exclaim",
        runner=AddExclamationStage,
        kind=StageKind.TRANSFORM,
        dependencies=("uppercase",),  # Runs after uppercase completes
    )
)
```

### Step 3: Create the Context

The `ContextSnapshot` carries input data and metadata through the pipeline:

```python
from uuid import uuid4
from stageflow.context import ContextSnapshot, RunIdentity

snapshot = ContextSnapshot(
    run_id=RunIdentity(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=None,
        interaction_id=uuid4(),
    ),
    topology="quickstart",
    execution_mode="default",
    input_text="hello world",  # Our input
)
```

### Step 4: Run the Pipeline

Build the graph and execute:

```python
import asyncio
from stageflow import StageContext, PipelineTimer
from stageflow.stages import StageInputs

async def main():
    # Build executable graph
    graph = pipeline.build()
    
    # Create execution context (StageInputs + StageContext)
    inputs = StageInputs(snapshot=snapshot)
    ctx = StageContext(
        snapshot=snapshot,
        inputs=inputs,
        stage_name="pipeline",
        timer=PipelineTimer(),
    )
    
    # Run the pipeline
    results = await graph.run(ctx)
    
    # Access results
    print(results["uppercase"].data)  # {'text': 'HELLO WORLD'}
    print(results["exclaim"].data)    # {'text': 'HELLO WORLD!!!', 'excited': True}

asyncio.run(main())
```

## Complete Example

Here's the full working code:

```python
import asyncio
from uuid import uuid4

from stageflow import Pipeline, StageContext, StageKind, StageOutput, PipelineTimer
from stageflow.context import ContextSnapshot, RunIdentity
from stageflow.helpers import LLMResponse
from stageflow.stages import StageInputs


class UppercaseStage:
    name = "uppercase"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        text = ctx.snapshot.input_text or ""
        return StageOutput.ok(text=text.upper())


class AddExclamationStage:
    name = "exclaim"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        text = ctx.inputs.get_from("uppercase", "text", default="")

        # Example: capture LLM metadata even if you are mocking it
        mock_llm = LLMResponse(
            content=f"{text}!!!",
            model="demo-mini",
            provider="mock",
            input_tokens=len(text),
            output_tokens=len(text) + 3,
        )

        return StageOutput.ok(
            text=mock_llm.content,
            excited=True,
            llm=mock_llm.to_dict(),
        )


async def main():
    # Build pipeline
    pipeline = (
        Pipeline()
        .with_stage("uppercase", UppercaseStage, StageKind.TRANSFORM)
        .with_stage(
            "exclaim",
            AddExclamationStage,
            StageKind.TRANSFORM,
            dependencies=("uppercase",),
        )
    )
    
    # Create context
    snapshot = ContextSnapshot(
        run_id=RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=None,
            interaction_id=uuid4(),
        ),
        topology="quickstart",
        execution_mode="default",
        input_text="hello world",
    )
    
    # Run
    graph = pipeline.build()
    ctx = StageContext(
        snapshot=snapshot,
        inputs=StageInputs(snapshot=snapshot),
        stage_name="pipeline",
        timer=PipelineTimer(),
    )
    results = await graph.run(ctx)
    
    # Output
    print(f"Input: hello world")
    print(f"After uppercase: {results['uppercase'].data['text']}")
    print(f"After exclaim: {results['exclaim'].data['text']}")

    # Drop-in telemetry: listen to streaming helpers
    from stageflow.helpers import ChunkQueue

    queue = ChunkQueue(event_emitter=lambda event, data: print(f"{event}: {data}"))
    await queue.put("demo")
    await queue.close()


if __name__ == "__main__":
    asyncio.run(main())
```

Output:
```
Input: hello world
After uppercase: HELLO WORLD
After exclaim: HELLO WORLD!!!
```

## What's Next?

Now that you've built your first pipeline, explore:

- [Core Concepts](concepts.md) — Understand stages, pipelines, and contexts in depth
- [Building Stages](../guides/stages.md) — Learn all the stage types and patterns
- [Parallel Execution](../examples/parallel.md) — Run stages concurrently
- [Adding Interceptors](../guides/interceptors.md) — Add logging, metrics, and timeouts
- [Observability](../guides/observability.md) — Wire streaming telemetry events and analytics exporters
- [Tools Guide](../guides/tools.md) — Parse LLM tool calls with `ToolRegistry.parse_and_resolve`
