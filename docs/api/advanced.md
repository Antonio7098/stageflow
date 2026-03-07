# Advanced API Surface

`stageflow.advanced` is the explicit import surface for runtime customization,
graph internals, and other non-beginner features.

Use `stageflow.api` for normal application code. Use `stageflow.advanced` when
you want the package structure itself to signal “this is advanced/runtime code.”

## Typical imports

```python
from stageflow.advanced import (
    ContextSizeInterceptor,
    ImmutabilityInterceptor,
    PipelineBuilder,
    UnifiedStageGraph,
    get_default_interceptors,
)
```

## What lives here

- interceptors and hardening controls
- graph builders and runtime graph types
- context internals such as `ContextSnapshot` and `RunIdentity`
- guard-retry strategies
- wide-event emitters and related observability hooks

## What does not move here

- beginner/default app code should still import from `stageflow.api`
- `PipelineRunner` remains in `stageflow.helpers` as a compatibility/utility helper
- interceptor result types such as `InterceptorResult` and `InterceptorContext` are available from `stageflow.advanced`

## Example

```python
from stageflow.advanced import ImmutabilityInterceptor
from stageflow.api import Pipeline

pipeline = Pipeline().with_stage("demo", DemoStage)
graph = pipeline.build(interceptors=[ImmutabilityInterceptor()])
results = await graph.run(ctx)
```