# Installation

## Requirements

Stageflow requires:
- **Python 3.11** or higher
- An asyncio-compatible runtime

## Installing from PyPI

```bash
pip install stageflow
```

## Installing from Source

Clone the repository and install in development mode:

```bash
git clone https://github.com/your-org/stageflow.git
cd stageflow
pip install -e .
```

## Optional Dependencies

Stageflow has optional dependencies for specific features:

```bash
# For development and testing
pip install stageflow[dev]

# For documentation generation
pip install stageflow[docs]
```

## Verifying Installation

Verify your installation by running:

```python
import stageflow
print(stageflow.__all__)
```

You should see a list of exported types including `Pipeline`, `Stage`, `StageOutput`, etc.

## Quick Verification

Run this minimal example to verify everything works:

```python
import asyncio
from stageflow import Pipeline, StageKind, StageOutput, StageContext
from stageflow.context import ContextSnapshot

class HelloStage:
    name = "hello"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        return StageOutput.ok(message="Hello, Stageflow!")

async def main():
    # Create a minimal context snapshot
    snapshot = ContextSnapshot(
        pipeline_run_id=None,
        request_id=None,
        session_id=None,
        user_id=None,
        org_id=None,
        interaction_id=None,
        topology=None,
        channel=None,
        execution_mode=None,
    )
    
    # Build the pipeline
    pipeline = Pipeline().with_stage("hello", HelloStage, StageKind.TRANSFORM)
    graph = pipeline.build()
    
    # Create context and run
    ctx = StageContext(snapshot=snapshot)
    results = await graph.run(ctx)
    
    print(results["hello"].data)  # {'message': 'Hello, Stageflow!'}

asyncio.run(main())
```

## Next Steps

- Continue to the [Quick Start](quickstart.md) guide to build your first real pipeline
- Read about [Core Concepts](concepts.md) to understand the framework architecture
