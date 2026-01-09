# Subpipeline Runs

This guide covers nested pipeline execution for complex workflows.

## Overview

Subpipelines allow a stage to spawn a child pipeline run. This is useful for:

- **Tool execution** that requires its own pipeline topology
- **Delegation** to specialized agents
- **Complex operations** that need isolation

## How It Works

```
Parent Pipeline
┌─────────────────────────────────────────────────────────────┐
│  [stage_a] → [stage_b] → [tool_executor] → [stage_c]       │
│                               │                             │
│                               ▼                             │
│                    ┌─────────────────────┐                  │
│                    │  Child Pipeline     │                  │
│                    │  [parse] → [exec]   │                  │
│                    └─────────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

## Forking Context

Use `PipelineContext.fork()` to create a child context:

```python
from uuid import uuid4
from stageflow.stages.context import PipelineContext

# Parent context
parent_ctx = PipelineContext(
    pipeline_run_id=uuid4(),
    request_id=uuid4(),
    session_id=uuid4(),
    user_id=uuid4(),
    org_id=uuid4(),
    interaction_id=uuid4(),
    topology="parent_pipeline",
    execution_mode="default",
)

# Fork for child pipeline
child_ctx = parent_ctx.fork(
    child_run_id=uuid4(),
    parent_stage_id="tool_executor",
    correlation_id=uuid4(),
    topology="child_pipeline",  # Optional: different topology
    execution_mode="tool_mode",  # Optional: different mode
)
```

## Child Context Properties

The child context:

- Has its own `pipeline_run_id`
- References parent via `parent_run_id` and `parent_stage_id`
- Gets a **read-only snapshot** of parent data
- Inherits auth context (`user_id`, `org_id`, `session_id`)
- Has its own fresh `data` dict and `artifacts` list

```python
# Check if context is a child run
if child_ctx.is_child_run:
    print(f"Parent run: {child_ctx.parent_run_id}")
    print(f"Parent stage: {child_ctx.parent_stage_id}")
    print(f"Correlation: {child_ctx.correlation_id}")

# Access parent data (read-only)
parent_value = child_ctx.get_parent_data("some_key", default=None)
```

## Implementing Subpipeline Execution

### Stage That Spawns Subpipeline

```python
from uuid import uuid4
from stageflow import StageContext, StageKind, StageOutput, Pipeline

class ToolExecutorStage:
    """Stage that executes tools via subpipelines."""
    
    name = "tool_executor"
    kind = StageKind.WORK

    def __init__(self, tool_pipeline_factory):
        self.tool_pipeline_factory = tool_pipeline_factory

    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs = ctx.config.get("inputs")
        tool_calls = inputs.get("tool_calls", []) if inputs else []
        
        results = []
        for tool_call in tool_calls:
            # Create child pipeline for this tool
            tool_pipeline = self.tool_pipeline_factory(tool_call.type)
            
            # Fork context for child run
            child_run_id = uuid4()
            correlation_id = uuid4()
            
            # Execute child pipeline
            result = await self._run_child_pipeline(
                parent_ctx=ctx,
                child_run_id=child_run_id,
                correlation_id=correlation_id,
                pipeline=tool_pipeline,
                tool_call=tool_call,
            )
            results.append(result)
        
        return StageOutput.ok(tool_results=results)

    async def _run_child_pipeline(
        self,
        parent_ctx,
        child_run_id,
        correlation_id,
        pipeline,
        tool_call,
    ):
        # Build child graph
        graph = pipeline.build()
        
        # Create child context (simplified - actual implementation uses PipelineContext)
        child_snapshot = ContextSnapshot(
            pipeline_run_id=child_run_id,
            request_id=parent_ctx.snapshot.request_id,
            session_id=parent_ctx.snapshot.session_id,
            user_id=parent_ctx.snapshot.user_id,
            org_id=parent_ctx.snapshot.org_id,
            interaction_id=parent_ctx.snapshot.interaction_id,
            topology=f"tool_{tool_call.type}",
            execution_mode="tool_execution",
            input_text=str(tool_call.payload),
        )
        
        child_ctx = StageContext(snapshot=child_snapshot)
        
        # Run child pipeline
        try:
            results = await graph.run(child_ctx)
            return {"success": True, "results": results}
        except Exception as e:
            return {"success": False, "error": str(e)}
```

## Correlation and Tracing

### Correlation IDs

Child runs maintain correlation with parent:

```python
# In events and logs
event_data = {
    "pipeline_run_id": str(child_ctx.pipeline_run_id),
    "parent_run_id": str(child_ctx.parent_run_id),
    "parent_stage_id": child_ctx.parent_stage_id,
    "correlation_id": str(child_ctx.correlation_id),
}
```

### Event Correlation

Events from child pipelines include parent references:

```python
# Child pipeline event
{
    "type": "stage.parse.completed",
    "data": {
        "pipeline_run_id": "child-uuid",
        "parent_run_id": "parent-uuid",
        "parent_stage_id": "tool_executor",
        "correlation_id": "action-uuid",
        ...
    }
}
```

## Error Handling

### Child Failures

Child failures bubble up to the parent:

```python
async def _run_child_pipeline(self, ...):
    try:
        results = await graph.run(child_ctx)
        return {"success": True, "results": results}
    except StageExecutionError as e:
        # Log with correlation
        logger.error(
            f"Child pipeline failed",
            extra={
                "parent_run_id": str(parent_ctx.pipeline_run_id),
                "child_run_id": str(child_run_id),
                "failed_stage": e.stage,
                "error": str(e.original),
            },
        )
        return {"success": False, "error": str(e), "stage": e.stage}
    except UnifiedPipelineCancelled as e:
        return {"success": False, "cancelled": True, "reason": e.reason}
```

### Cancellation Propagation

Parent cancellation should cascade to children:

```python
async def execute(self, ctx: StageContext) -> StageOutput:
    # Check for cancellation before spawning children
    if ctx.config.get("canceled"):
        return StageOutput.cancel(reason="Parent cancelled")
    
    # Track child tasks for cancellation
    child_tasks = []
    
    for tool_call in tool_calls:
        task = asyncio.create_task(self._run_child(tool_call))
        child_tasks.append(task)
    
    # Wait with cancellation support
    try:
        results = await asyncio.gather(*child_tasks)
    except asyncio.CancelledError:
        # Cancel all children
        for task in child_tasks:
            task.cancel()
        await asyncio.gather(*child_tasks, return_exceptions=True)
        raise
```

## Data Isolation

### Read-Only Parent Data

Children get a frozen snapshot of parent data:

```python
from stageflow.utils.frozen import FrozenDict

# In fork()
child_ctx = PipelineContext(
    ...
    _parent_data=FrozenDict(parent_ctx.data),  # Read-only copy
)

# In child stage
parent_value = ctx.get_parent_data("key")  # Safe read
# ctx.data is fresh dict for child's own outputs
```

### Output Isolation

Child outputs don't pollute parent context:

```python
# Child writes to its own data dict
child_ctx.data["child_result"] = "value"

# Parent data is unchanged
assert "child_result" not in parent_ctx.data

# Results returned explicitly
return {"child_output": child_ctx.data}
```

## Use Cases

### Tool Execution

```python
def create_tool_pipeline(tool_type: str) -> Pipeline:
    """Create pipeline for specific tool type."""
    if tool_type == "EDIT_DOCUMENT":
        return (
            Pipeline()
            .with_stage("parse", ParseEditStage, StageKind.TRANSFORM)
            .with_stage("validate", ValidateEditStage, StageKind.GUARD, dependencies=("parse",))
            .with_stage("execute", ExecuteEditStage, StageKind.WORK, dependencies=("validate",))
        )
    elif tool_type == "SEARCH":
        return (
            Pipeline()
            .with_stage("parse", ParseSearchStage, StageKind.TRANSFORM)
            .with_stage("search", SearchStage, StageKind.WORK, dependencies=("parse",))
            .with_stage("rank", RankResultsStage, StageKind.TRANSFORM, dependencies=("search",))
        )
    else:
        raise ValueError(f"Unknown tool type: {tool_type}")
```

### Agent Delegation

```python
class DelegatingAgentStage:
    """Agent that delegates to specialized sub-agents."""
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        intent = self._classify_intent(ctx.snapshot.input_text)
        
        if intent == "document_edit":
            # Delegate to document agent via subpipeline
            result = await self._delegate_to_agent(
                ctx,
                agent_pipeline="document_agent",
                context_enrichment={"document_id": self._extract_doc_id(ctx)},
            )
        elif intent == "code_review":
            result = await self._delegate_to_agent(
                ctx,
                agent_pipeline="code_review_agent",
            )
        else:
            # Handle directly
            result = await self._handle_directly(ctx)
        
        return StageOutput.ok(response=result)
```

## Best Practices

### 1. Limit Nesting Depth

Avoid deeply nested subpipelines:

```python
# Good: Single level of nesting
Parent → Child

# Avoid: Deep nesting
Parent → Child → Grandchild → Great-grandchild
```

### 2. Keep Children Focused

Each child pipeline should have a specific purpose:

```python
# Good: Focused child pipeline
edit_pipeline = Pipeline()
    .with_stage("parse", ParseStage, ...)
    .with_stage("execute", ExecuteStage, ...)

# Avoid: Kitchen-sink child pipeline
everything_pipeline = Pipeline()
    .with_stage("parse", ...)
    .with_stage("validate", ...)
    .with_stage("enrich", ...)
    .with_stage("execute", ...)
    .with_stage("notify", ...)
    .with_stage("audit", ...)
```

### 3. Propagate Correlation IDs

Always include correlation IDs in events and logs:

```python
logger.info(
    "Child pipeline started",
    extra={
        "parent_run_id": str(parent_run_id),
        "child_run_id": str(child_run_id),
        "correlation_id": str(correlation_id),
    },
)
```

### 4. Handle Timeouts

Set appropriate timeouts for child pipelines:

```python
async def _run_child_pipeline(self, ...):
    try:
        results = await asyncio.wait_for(
            graph.run(child_ctx),
            timeout=30.0,  # 30 second timeout
        )
        return {"success": True, "results": results}
    except asyncio.TimeoutError:
        return {"success": False, "error": "Child pipeline timed out"}
```

## Next Steps

- [Custom Interceptors](custom-interceptors.md) — Build middleware for subpipelines
- [Error Handling](errors.md) — Handle subpipeline failures
- [Testing](testing.md) — Test subpipeline execution
