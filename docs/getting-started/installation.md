# Installation

## Requirements

Stageflow requires:
- **Python 3.11** or higher
- An asyncio-compatible runtime

## Installing from PyPI

```bash
pip install stageflow-core
```

## Installing from Source

Clone the repository and install in development mode:

```bash
git clone https://github.com/Antonio7098/stageflow.git
cd stageflow
pip install -e .
```

## Optional Dependencies

Stageflow has optional dependencies for specific features:

```bash
# For development, testing, and documentation
pip install stageflow-core[dev]
```

## Verifying Installation

Verify your installation by running:

```python
import stageflow
print(stageflow.__all__)
```

You should see a list of exported types including `Pipeline`, `Stage`, `StageOutput`, etc.

Stageflow also exports helper modules—confirm the new provider response dataclasses are available:

```python
from stageflow.helpers import LLMResponse, STTResponse, TTSResponse

print(LLMResponse(model="mock", provider="demo", content="hi"))
```

If this import works, your environment is ready for deterministic provider metadata handling in later guides.

## Quick Verification

Run this minimal example to verify everything works:

```python
import asyncio
from stageflow import Pipeline, PipelineContext, StageKind, StageOutput, StageContext

class HelloStage:
    name = "hello"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        return StageOutput.ok(message="Hello, Stageflow!")

async def main():
    # Build the pipeline
    pipeline = Pipeline().with_stage("hello", HelloStage, StageKind.TRANSFORM)
    graph = pipeline.build()

    # PipelineContext is the single entry-point context.
    pipeline_ctx = PipelineContext(input_text="Hello, Stageflow!")
    results = await graph.run(pipeline_ctx)
    
    print(results["hello"].data)  # {'message': 'Hello, Stageflow!'}

    # Optional: emit quick telemetry from the queue helpers
    from stageflow.helpers import ChunkQueue

    q = ChunkQueue(event_emitter=lambda event, data: print(event, data))
    await q.put("warmup")
    await q.close()

asyncio.run(main())
```

## Next Steps

- Continue to the [Quick Start](quickstart.md) guide to build your first real pipeline
- Read about [Core Concepts](concepts.md) to understand the framework architecture
- Jump to [Observability](../guides/observability.md) once you're ready to wire telemetry, streaming events, and analytics exporters
