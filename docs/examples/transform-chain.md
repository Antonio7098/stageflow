# Transform Chain Example

This example demonstrates a linear chain of transform stages, where each stage processes the output of the previous one.

## Overview

```
[uppercase] → [reverse] → [summarize]
```

Three TRANSFORM stages in sequence, each modifying the text.

## The Stages

### UppercaseStage

```python
import asyncio
from stageflow import StageContext, StageKind, StageOutput


class UppercaseStage:
    """Transform text to uppercase."""

    name = "uppercase"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        await asyncio.sleep(0.15)

        # Get input from snapshot or upstream stage
        inputs = ctx.config.get("inputs")
        if inputs:
            text = inputs.get("text") or inputs.snapshot.input_text or ""
        else:
            text = ctx.snapshot.input_text or ""

        result = text.upper()
        return StageOutput.ok(text=result, transformed=True)
```

### ReverseStage

```python
class ReverseStage:
    """Reverse the text."""

    name = "reverse"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        await asyncio.sleep(0.15)

        inputs = ctx.config.get("inputs")
        if inputs:
            text = inputs.get("text") or inputs.snapshot.input_text or ""
        else:
            text = ctx.snapshot.input_text or ""

        result = text[::-1]
        return StageOutput.ok(text=result, reversed=True)
```

### SummarizeStage

```python
class SummarizeStage:
    """Summarize/truncate text (mock summarization)."""

    name = "summarize"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        await asyncio.sleep(0.2)

        inputs = ctx.config.get("inputs")
        if inputs:
            text = inputs.get("text") or inputs.snapshot.input_text or ""
        else:
            text = ctx.snapshot.input_text or ""

        # Simple truncation as mock summarization
        if len(text) > 100:
            summary = text[:100] + "..."
        else:
            summary = text

        return StageOutput.ok(
            text=summary,
            summary=summary,
            original_length=len(text),
            summarized=True,
        )
```

## The Pipeline

```python
from stageflow import Pipeline, StageKind


def create_transform_pipeline() -> Pipeline:
    """Create a linear chain of transform stages.
    
    DAG:
        [uppercase] → [reverse] → [summarize]
    """
    return (
        Pipeline()
        .with_stage(
            name="uppercase",
            runner=UppercaseStage,
            kind=StageKind.TRANSFORM,
        )
        .with_stage(
            name="reverse",
            runner=ReverseStage,
            kind=StageKind.TRANSFORM,
            dependencies=("uppercase",),  # Waits for uppercase
        )
        .with_stage(
            name="summarize",
            runner=SummarizeStage,
            kind=StageKind.TRANSFORM,
            dependencies=("reverse",),  # Waits for reverse
        )
    )
```

### Key Points

1. **Dependencies**: Each stage lists its predecessor in `dependencies`
2. **Sequential Execution**: Stages run one after another
3. **Data Flow**: Each stage reads `text` from the previous stage's output

## Complete Example

```python
import asyncio
from uuid import uuid4

from stageflow import Pipeline, StageContext, StageKind, StageOutput
from stageflow.context import ContextSnapshot


class UppercaseStage:
    name = "uppercase"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs = ctx.config.get("inputs")
        text = inputs.get("text") if inputs else None
        text = text or ctx.snapshot.input_text or ""
        return StageOutput.ok(text=text.upper())


class ReverseStage:
    name = "reverse"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs = ctx.config.get("inputs")
        text = inputs.get("text") if inputs else ""
        return StageOutput.ok(text=text[::-1])


class SummarizeStage:
    name = "summarize"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs = ctx.config.get("inputs")
        text = inputs.get("text") if inputs else ""
        summary = text[:50] + "..." if len(text) > 50 else text
        return StageOutput.ok(text=summary, original_length=len(text))


async def main():
    # Create the pipeline
    pipeline = (
        Pipeline()
        .with_stage("uppercase", UppercaseStage, StageKind.TRANSFORM)
        .with_stage("reverse", ReverseStage, StageKind.TRANSFORM, dependencies=("uppercase",))
        .with_stage("summarize", SummarizeStage, StageKind.TRANSFORM, dependencies=("reverse",))
    )
    
    # Build and create context
    graph = pipeline.build()
    
    snapshot = ContextSnapshot(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=None,
        interaction_id=uuid4(),
        topology="transform_chain",
        channel="text",
        execution_mode="default",
        input_text="Hello, this is a test of the transform chain!",
    )
    
    ctx = StageContext(snapshot=snapshot)
    
    # Run
    results = await graph.run(ctx)
    
    # Show transformation at each step
    print("Input:", snapshot.input_text)
    print()
    print("After uppercase:", results["uppercase"].data["text"])
    print("After reverse:", results["reverse"].data["text"])
    print("After summarize:", results["summarize"].data["text"])


if __name__ == "__main__":
    asyncio.run(main())
```

## Output

```
Input: Hello, this is a test of the transform chain!

After uppercase: HELLO, THIS IS A TEST OF THE TRANSFORM CHAIN!
After reverse: !NIAHC MROFSNART EHT FO TSET A SI SIHT ,OLLEH
After summarize: !NIAHC MROFSNART EHT FO TSET A SI SIHT ,OLLEH
```

## Data Flow Explained

```
┌─────────────────────────────────────────────────────────────┐
│ ContextSnapshot                                              │
│   input_text: "Hello, this is a test..."                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ UppercaseStage                                               │
│   reads: ctx.snapshot.input_text                            │
│   outputs: {text: "HELLO, THIS IS A TEST..."}               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ ReverseStage                                                 │
│   reads: inputs.get("text") → "HELLO, THIS IS A TEST..."    │
│   outputs: {text: "...TSET A SI SIHT ,OLLEH"}               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ SummarizeStage                                               │
│   reads: inputs.get("text") → "...TSET A SI SIHT ,OLLEH"    │
│   outputs: {text: "...TSET A SI SIHT ,OLLEH", ...}          │
└─────────────────────────────────────────────────────────────┘
```

## Accessing Specific Stage Outputs

```python
# Get output from a specific stage
inputs = ctx.config.get("inputs")
if inputs:
    # Get from any upstream stage
    text = inputs.get("text")
    
    # Get from a specific stage
    uppercase_text = inputs.get_from("uppercase", "text")
```

## Conditional Chains

You can make stages conditional:

```python
pipeline = (
    Pipeline()
    .with_stage("uppercase", UppercaseStage, StageKind.TRANSFORM)
    .with_stage(
        "reverse",
        ReverseStage,
        StageKind.TRANSFORM,
        dependencies=("uppercase",),
        conditional=True,  # May be skipped
    )
    .with_stage("summarize", SummarizeStage, StageKind.TRANSFORM, dependencies=("reverse",))
)
```

A conditional stage can return `StageOutput.skip()` to be skipped:

```python
class ConditionalReverseStage:
    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs = ctx.config.get("inputs")
        text = inputs.get("text") if inputs else ""
        
        # Skip if text is too short
        if len(text) < 10:
            return StageOutput.skip(reason="Text too short to reverse")
        
        return StageOutput.ok(text=text[::-1])
```

## Next Steps

- [Parallel Enrichment](parallel.md) — Stages running concurrently
- [Full Pipeline](full.md) — Complete pipeline with all features
- [Context & Data Flow](../guides/context.md) — Deep dive into data passing
