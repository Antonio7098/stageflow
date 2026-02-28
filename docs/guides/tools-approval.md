# Tools & Approval Workflows Guide

This guide covers tool execution, human-in-the-loop (HITL) approvals, and rollback patterns in Stageflow.

## Overview

Stageflow provides three main building blocks:

- `ToolRegistry` for discovery and legacy tool execution
- `AdvancedToolExecutor` for behavior gating, approvals, undo, and telemetry
- `ApprovalService` + `UndoStore` for HITL and rollback flows

## Tool Registry

### Registering Tools

```python
from stageflow.tools import BaseTool, get_tool_registry
from stageflow.tools.base import ToolInput, ToolOutput


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate basic expressions"
    action_type = "CALCULATE"

    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        expr = str(input.action.payload.get("expression", "0"))
        return ToolOutput(success=True, data={"result": eval(expr)})


registry = get_tool_registry()
registry.register(CalculatorTool())
```

### Parsing LLM Tool Calls

```python
resolved, unresolved = registry.parse_and_resolve(tool_calls)

for call in unresolved:
    ctx.try_emit_event("tools.unresolved", {"call_id": call.call_id, "error": call.error})

for call in resolved:
    output = await call.tool.execute(
        ToolInput(action=type("A", (), {"type": call.name, "payload": call.arguments})()),
        ctx=ctx.to_dict(),
    )
```

## Legacy ToolExecutor (Plan Stage)

`ToolExecutor` is a stage-oriented executor that consumes a plan object (`plan.actions`) and a `PipelineContext`.

```python
from stageflow.tools import ToolExecutor

executor = ToolExecutor()
result = await executor.execute(ctx=pipeline_ctx, plan=plan)

print(result.actions_executed)
print(result.actions_failed)
```

## AdvancedToolExecutor

Use this for approvals, undo metadata, and richer tool lifecycle events.

```python
from dataclasses import dataclass
from uuid import UUID, uuid4

from stageflow.tools import AdvancedToolExecutor, ToolDefinition, ToolInput, ToolOutput
from stageflow.testing import create_test_stage_context


@dataclass(frozen=True)
class Action:
    id: UUID
    type: str
    payload: dict


async def weather_handler(input: ToolInput) -> ToolOutput:
    city = input.payload.get("location", "unknown")
    return ToolOutput.ok(data={"location": city, "temp_f": 72})


executor = AdvancedToolExecutor()
executor.register(
    ToolDefinition(
        name="weather",
        action_type="GET_WEATHER",
        description="Fetch weather by location",
        handler=weather_handler,
        allowed_behaviors=("practice", "prod"),
    )
)

ctx = create_test_stage_context(execution_mode="practice")
action = Action(id=uuid4(), type="GET_WEATHER", payload={"location": "Austin"})
output = await executor.execute(action, ctx)
print(output.data)
```

## Approval Workflow

```python
import asyncio
from uuid import uuid4

from stageflow.tools import ApprovalService

service = ApprovalService(default_timeout_seconds=300)

request = await service.request_approval(
    action_id=uuid4(),
    tool_name="delete_account",
    approval_message="Delete account for user@example.com?",
    payload_summary={"user_id": "user@example.com"},
)

# In real systems, this is triggered by UI action.
await service.record_decision(request.id, granted=True, reason="Approved by on-call")

decision = await service.await_decision(request.id, timeout_seconds=60)
if decision.granted:
    print("approved")
```

## Undo Workflow

```python
from uuid import uuid4

from stageflow.tools import get_undo_store

undo_store = get_undo_store()
action_id = uuid4()

await undo_store.store(
    action_id=action_id,
    tool_name="toggle_feature",
    undo_data={"enabled_before": False},
)

metadata = await undo_store.get(action_id)
if metadata is not None:
    # Run your undo logic, then clear
    await undo_store.delete(action_id)
```

## Context Adapters

If your legacy code passes dict contexts, adapt it to the execution-context protocol:

```python
from stageflow.tools import adapt_context

legacy_ctx = {
    "pipeline_run_id": "00000000-0000-0000-0000-000000000001",
    "request_id": "00000000-0000-0000-0000-000000000002",
    "execution_mode": "practice",
}

ctx = adapt_context(legacy_ctx)
print(ctx.execution_mode)
```

## Testing

```python
from stageflow.helpers import MockToolExecutor

executor = MockToolExecutor(
    tools={
        "calculator": lambda args: {"result": eval(args["expression"])},
    },
    latency_ms=10,
)

result = await executor.execute("calculator", {"expression": "2+2"})
assert result.success
assert result.output["result"] == 4
```

## Best Practices

1. Prefer `AdvancedToolExecutor` for new builds.
2. Keep approval payloads minimal and human-readable.
3. Store undo metadata only for truly reversible actions.
4. Emit `tools.unresolved` whenever model tool calls fail schema/registry resolution.
