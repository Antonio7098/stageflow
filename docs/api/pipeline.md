# Pipeline API Reference

This document provides the API reference for pipeline building and execution.

## Pipeline

```python
from stageflow import Pipeline
```

Builder for composing stages into a pipeline DAG.

### Constructor

```python
Pipeline(stages: dict[str, UnifiedStageSpec] = None)
```

### Methods

#### `with_stage(name, runner, kind, dependencies=None, conditional=False) -> Pipeline`

Add a stage to the pipeline (fluent builder).

**Parameters:**
- `name`: `str` — Unique stage name within the pipeline
- `runner`: `type[Stage] | Stage` — Stage class or instance
- `kind`: `StageKind` — Stage categorization
- `dependencies`: `tuple[str, ...] | None` — Names of stages that must complete first
- `conditional`: `bool` — If True, stage may be skipped based on context

**Returns:** New `Pipeline` instance (immutable)

```python
pipeline = (
    Pipeline()
    .with_stage("input", InputStage, StageKind.TRANSFORM)
    .with_stage("process", ProcessStage, StageKind.TRANSFORM, dependencies=("input",))
)
```

#### `compose(other: Pipeline) -> Pipeline`

Merge stages from another pipeline.

**Parameters:**
- `other`: `Pipeline` — Pipeline to merge

**Returns:** New `Pipeline` with merged stages

```python
base = Pipeline().with_stage("a", StageA, StageKind.TRANSFORM)
extension = Pipeline().with_stage("b", StageB, StageKind.TRANSFORM)
merged = base.compose(extension)
```

#### `build() -> StageGraph`

Generate executable DAG for the orchestrator.

**Returns:** `StageGraph` ready for execution

**Raises:** `ValueError` if pipeline is empty or dependencies are invalid

```python
graph = pipeline.build()
results = await graph.run(ctx)
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `stages` | `dict[str, UnifiedStageSpec]` | Mapping of stage name to spec |

---

## UnifiedStageSpec

```python
from stageflow import UnifiedStageSpec
```

Specification for a stage in the pipeline DAG.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Stage name |
| `runner` | `type[Stage] \| Stage` | Stage class or instance |
| `kind` | `StageKind` | Stage categorization |
| `dependencies` | `tuple[str, ...]` | Stage dependencies |
| `conditional` | `bool` | Whether stage can be skipped |

---

## StageGraph

```python
from stageflow import StageGraph
```

Dependency-driven DAG executor with parallel execution.

### Constructor

```python
StageGraph(specs: Iterable[StageSpec], interceptors: list[BaseInterceptor] | None = None)
```

### Methods

#### `run(ctx: StageContext) -> dict[str, StageOutput]`

Execute the DAG with the given context.

**Parameters:**
- `ctx`: `StageContext` — Execution context

**Returns:** Dict mapping stage name to `StageOutput`

**Raises:**
- `RuntimeError` — If deadlock detected
- `StageExecutionError` — If a stage fails

```python
results = await graph.run(ctx)
print(results["my_stage"].data)
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `stage_specs` | `list[StageSpec]` | List of stage specifications |

---

## StageSpec

```python
from stageflow import StageSpec
```

Low-level specification for a stage (used by StageGraph).

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Stage name |
| `runner` | `StageRunner` | Callable that runs the stage |
| `dependencies` | `tuple[str, ...]` | Stage dependencies |
| `conditional` | `bool` | Whether stage can be skipped |

---

## PipelineRegistry

```python
from stageflow import PipelineRegistry, pipeline_registry
```

Registry for pipeline instances with lazy registration.

### Methods

#### `register(name: str, pipeline: Pipeline) -> None`

Register a pipeline instance.

```python
pipeline_registry.register("chat", create_chat_pipeline())
```

#### `get(name: str) -> Pipeline`

Get a pipeline by name.

**Raises:** `KeyError` if not found

```python
pipeline = pipeline_registry.get("chat")
```

#### `list() -> list[str]`

List all registered pipeline names.

```python
names = pipeline_registry.list()  # ["chat", "voice", ...]
```

#### `__contains__(name: str) -> bool`

Check if pipeline name is registered.

```python
if "chat" in pipeline_registry:
    pipeline = pipeline_registry.get("chat")
```

### Global Instance

```python
from stageflow import pipeline_registry

# Use the global registry
pipeline_registry.register("my_pipeline", my_pipeline)
pipeline = pipeline_registry.get("my_pipeline")
```

---

## Exceptions

### StageExecutionError

```python
from stageflow import StageExecutionError
```

Raised when a stage inside a StageGraph fails.

**Attributes:**
- `stage`: `str` — Name of the failed stage
- `original`: `Exception` — Original exception
- `recoverable`: `bool` — Whether error is recoverable

### UnifiedPipelineCancelled

```python
from stageflow.pipeline.dag import UnifiedPipelineCancelled
```

Raised when pipeline is cancelled by a stage (not an error).

**Attributes:**
- `stage`: `str` — Stage that cancelled
- `reason`: `str` — Cancellation reason
- `results`: `dict[str, StageOutput]` — Partial results

```python
try:
    results = await graph.run(ctx)
except UnifiedPipelineCancelled as e:
    print(f"Cancelled by {e.stage}: {e.reason}")
    partial = e.results
```

---

## Usage Example

```python
from stageflow import (
    Pipeline,
    PipelineRegistry,
    StageKind,
    StageContext,
    StageOutput,
    StageExecutionError,
    pipeline_registry,
)
from stageflow.context import ContextSnapshot
from stageflow.pipeline.dag import UnifiedPipelineCancelled

# Define stages
class InputStage:
    name = "input"
    kind = StageKind.TRANSFORM
    async def execute(self, ctx): return StageOutput.ok(text="hello")

class ProcessStage:
    name = "process"
    kind = StageKind.TRANSFORM
    async def execute(self, ctx):
        inputs = ctx.config.get("inputs")
        text = inputs.get("text") if inputs else ""
        return StageOutput.ok(result=text.upper())

# Build pipeline
pipeline = (
    Pipeline()
    .with_stage("input", InputStage, StageKind.TRANSFORM)
    .with_stage("process", ProcessStage, StageKind.TRANSFORM, dependencies=("input",))
)

# Register
pipeline_registry.register("example", pipeline)

# Execute
async def run():
    graph = pipeline.build()
    snapshot = ContextSnapshot(...)
    ctx = StageContext(snapshot=snapshot)
    
    try:
        results = await graph.run(ctx)
        print(results["process"].data["result"])  # "HELLO"
    except StageExecutionError as e:
        print(f"Stage {e.stage} failed: {e.original}")
    except UnifiedPipelineCancelled as e:
        print(f"Cancelled: {e.reason}")
```
