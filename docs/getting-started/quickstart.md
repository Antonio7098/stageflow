# Quick Start

This guide walks you through building your first stageflow pipeline in 5 minutes.

## Your First Pipeline

Let's build a simple pipeline that transforms user input through multiple stages.

### Step 1: Define Your Stages

Stages are the building blocks of pipelines. Each stage implements the `Stage` protocol:

```python
from stageflow.api import StageContext, StageKind, stage_metadata

@stage_metadata(name="uppercase", kind=StageKind.TRANSFORM)
class UppercaseStage:
    """Transform text to uppercase."""

    async def execute(self, ctx: StageContext) -> dict[str, str]:
        # Get input from the context snapshot
        text = ctx.snapshot.input_text or ""

        # Transform and return
        return {"text": text.upper()}


@stage_metadata(name="exclaim", kind=StageKind.TRANSFORM)
class AddExclamationStage:
    """Add exclamation marks to text."""

    async def execute(self, ctx: StageContext) -> dict[str, object]:
        # Get output from previous stage via StageInputs
        text = ctx.inputs.get_from("uppercase", "text", default="")

        # Transform and return
        return {"text": f"{text}!!!", "excited": True}
```

### Step 2: Build the Pipeline

Use the `Pipeline` builder to compose stages into a DAG:

```python
from stageflow.api import Pipeline, stage

pipeline = Pipeline.from_stages(
    stage("uppercase", UppercaseStage),
    stage("exclaim", AddExclamationStage, after="uppercase"),
)
```

Use `after=` for simple tutorial-style chains like this. Use `dependencies=`
when a stage waits on multiple upstream stages or when you want to emphasize the
full DAG edge list explicitly.

### Step 3: Run It (Recommended)

For most projects, call `pipeline.run(...)` directly. This is the canonical
execution verb for Stageflow application code.

```python
import asyncio

async def main():
    results = await pipeline.run(
        input_text="hello world",
        topology="quickstart",
        execution_mode="default",
    )

    # Access results by stage name
    print(results.data("uppercase"))  # {'text': 'HELLO WORLD'}
    print(results.data("exclaim"))    # {'text': 'HELLO WORLD!!!', 'excited': True}

asyncio.run(main())
```

### Step 4: Manual Context Wiring (Advanced)

Use manual wiring only when you need full control over IDs, metadata, or
custom event sinks.

```python
import asyncio

from stageflow.api import PipelineContext

async def main():
    pipeline_ctx = PipelineContext(
        input_text="hello world",
        topology="quickstart",
        execution_mode="default",
    )

    results = await pipeline.run(pipeline_ctx)

asyncio.run(main())
```

Add explicit IDs only when you need correlation metadata; they are optional on
the normal path.

If you prefer a slightly more app-like alias in a quick script,
`pipeline.invoke("hello world")` works too. Treat it as a convenience alias,
not the primary API.

### About `PipelineContext`

`PipelineContext` is the caller-facing context you pass to `pipeline.run(...)`.
Most application code only needs this type. `StageContext` is derived internally
for stage execution.

> **Testing tip**: When you only need to run a single stage in isolation,
> use `stageflow.testing.create_test_stage_context()` instead of
> manually wiring `StageInputs` and `PipelineTimer`. It produces a
> ready-to-use `StageContext` with sensible defaults and optional
> `prior_outputs` so you can focus on the stage logic itself.

## Detecting & Preventing Cycles

Stageflow validates pipelines at build time, but you can catch dependency
issues even earlier by running the lint pass while you iterate. The
`stageflow.cli.lint_pipeline()` helper checks for:

- Circular dependencies
- Missing or misspelled dependency names
- Self-dependencies and orphaned stages

```python
from stageflow.api import Pipeline, StageKind
from stageflow.cli.lint import lint_pipeline

pipeline = (
    Pipeline()
    .with_stage("a", StageA, StageKind.TRANSFORM, dependencies=("c",))
    .with_stage("b", StageB, StageKind.TRANSFORM, dependencies=("a",))
    .with_stage("c", StageC, StageKind.TRANSFORM, dependencies=("b",))
)

lint_result = lint_pipeline(pipeline)
if not lint_result.valid:
    for issue in lint_result.issues:
        print(issue.message)
```

For cycles, the pipeline builder raises `CycleDetectedError`, which
contains structured troubleshooting metadata (error code, fix hint, docs
link). Breaking a cycle is as simple as removing one dependency in the
loop or routing through a dedicated router stage.

> **Tip**: Run `stageflow cli lint` in CI to block regressions—its output
> mirrors the structured `ContractErrorInfo` that Stageflow surfaces at
> runtime, making it easier to share remediation hints across your team.

## Complete Example

Here's the full working code:

```python
import asyncio

from stageflow.api import Pipeline, StageContext, StageKind, stage, stage_metadata
from stageflow.helpers import LLMResponse


@stage_metadata(name="uppercase", kind=StageKind.TRANSFORM)
class UppercaseStage:
    async def execute(self, ctx: StageContext) -> dict[str, str]:
        text = ctx.snapshot.input_text or ""
        return {"text": text.upper()}


@stage_metadata(name="exclaim", kind=StageKind.TRANSFORM)
class AddExclamationStage:
    async def execute(self, ctx: StageContext) -> dict[str, object]:
        text = ctx.inputs.get_from("uppercase", "text", default="")

        # Example: capture LLM metadata even if you are mocking it
        mock_llm = LLMResponse(
            content=f"{text}!!!",
            model="demo-mini",
            provider="mock",
            input_tokens=len(text),
            output_tokens=len(text) + 3,
        )

        return {"text": mock_llm.content, "excited": True, "llm": mock_llm.to_dict()}


async def main():
    # Build pipeline
    pipeline = Pipeline.from_stages(
        stage("uppercase", UppercaseStage),
        stage("exclaim", AddExclamationStage, after="uppercase"),
    )

    results = await pipeline.run(
        input_text="hello world",
        topology="quickstart",
        execution_mode="default",
    )

    # Output
    print(f"Input: hello world")
    print(f"After uppercase: {results.data('uppercase')['text']}")
    print(f"After exclaim: {results.data('exclaim')['text']}")


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
