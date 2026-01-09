"""Complex pipeline demonstrating unified tool system with ExecutionContext.

This pipeline showcases:
- AdvancedToolExecutor with StageContext (ExecutionContext protocol)
- Behavior gating for tools
- Full event lifecycle observability
- Multiple stages with tool execution
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from stageflow import Pipeline, StageContext, StageKind, StageOutput
from stageflow.tools import (
    AdvancedToolExecutor,
    ToolDefinition,
    ToolExecutorConfig,
    ToolInput,
    ToolOutput,
)


@dataclass(frozen=True)
class Action:
    """Action for tool execution."""
    id: UUID
    type: str
    payload: dict[str, Any]


# Tool handlers
async def echo_handler(input: ToolInput) -> ToolOutput:
    """Echo tool - returns the input payload."""
    return ToolOutput.ok(
        data={"echoed": input.payload, "tool": input.tool_name},
    )


async def transform_handler(input: ToolInput) -> ToolOutput:
    """Transform tool - transforms text to uppercase."""
    text = input.payload.get("text", "")
    return ToolOutput.ok(
        data={"original": text, "transformed": text.upper()},
    )


async def validate_handler(input: ToolInput) -> ToolOutput:
    """Validate tool - validates input data."""
    data = input.payload.get("data", {})
    required_fields = input.payload.get("required_fields", [])

    missing = [f for f in required_fields if f not in data]
    if missing:
        return ToolOutput.fail(f"Missing required fields: {missing}")

    return ToolOutput.ok(data={"valid": True, "fields_checked": required_fields})


async def restricted_handler(input: ToolInput) -> ToolOutput:
    """Restricted tool - only available in doc_edit mode."""
    return ToolOutput.ok(
        data={"message": "Restricted action executed", "behavior": input.behavior},
    )


class UnifiedToolStage:
    """Stage demonstrating unified tool execution with ExecutionContext."""

    name = "unified_tool"
    kind = StageKind.TRANSFORM

    def __init__(self):
        self.executor = AdvancedToolExecutor(
            config=ToolExecutorConfig(emit_events=True)
        )
        self._register_tools()

    def _register_tools(self) -> None:
        """Register tools with various configurations."""
        # Universal tool - available in all behaviors
        self.executor.register(ToolDefinition(
            name="echo",
            action_type="ECHO",
            handler=echo_handler,
            description="Echoes input payload",
        ))

        # Transform tool - available in all behaviors
        self.executor.register(ToolDefinition(
            name="transform",
            action_type="TRANSFORM",
            handler=transform_handler,
            description="Transforms text to uppercase",
        ))

        # Validate tool - available in all behaviors
        self.executor.register(ToolDefinition(
            name="validate",
            action_type="VALIDATE",
            handler=validate_handler,
            description="Validates input data",
        ))

        # Restricted tool - only in doc_edit and practice modes
        self.executor.register(ToolDefinition(
            name="restricted",
            action_type="RESTRICTED",
            handler=restricted_handler,
            description="Restricted action",
            allowed_behaviors=("doc_edit", "practice"),
        ))

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Execute tools based on input."""
        inputs = ctx.config.get("inputs")
        input_text = inputs.snapshot.input_text or "" if inputs else ctx.snapshot.input_text or ""

        # Emit stage started event
        ctx.try_emit_event("stage.unified_tool.processing", {
            "input_text": input_text,
            "execution_mode": ctx.execution_mode,
        })

        # Parse actions from input
        actions = self._parse_actions(input_text)
        results = []

        for action in actions:
            try:
                # Execute using AdvancedToolExecutor with StageContext
                output = await self.executor.execute(action, ctx)
                results.append({
                    "action": action.type,
                    "success": output.success,
                    "data": output.data,
                })

                # Emit success event
                ctx.try_emit_event("tool.execution.success", {
                    "action_type": action.type,
                    "action_id": str(action.id),
                })

            except Exception as e:
                results.append({
                    "action": action.type,
                    "success": False,
                    "error": str(e),
                })

                # Emit failure event
                ctx.try_emit_event("tool.execution.error", {
                    "action_type": action.type,
                    "error": str(e),
                })

        return StageOutput.ok(
            results=results,
            actions_count=len(actions),
            successful_count=sum(1 for r in results if r["success"]),
        )

    def _parse_actions(self, input_text: str) -> list[Action]:
        """Parse input text into actions."""
        actions = []
        lower = input_text.lower()

        if "echo" in lower:
            actions.append(Action(
                id=uuid4(),
                type="ECHO",
                payload={"message": input_text},
            ))

        if "transform" in lower:
            actions.append(Action(
                id=uuid4(),
                type="TRANSFORM",
                payload={"text": input_text},
            ))

        if "validate" in lower:
            actions.append(Action(
                id=uuid4(),
                type="VALIDATE",
                payload={
                    "data": {"name": "test", "value": 42},
                    "required_fields": ["name", "value"],
                },
            ))

        if "restricted" in lower:
            actions.append(Action(
                id=uuid4(),
                type="RESTRICTED",
                payload={},
            ))

        return actions


class EnrichmentStage:
    """Stage that enriches context with additional data."""

    name = "enrichment"
    kind = StageKind.ENRICH

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Enrich context with metadata."""
        ctx.try_emit_event("stage.enrichment.started", {})

        enrichment_data = {
            "timestamp": ctx.started_at.isoformat(),
            "execution_mode": ctx.execution_mode,
            "has_input": ctx.snapshot.input_text is not None,
        }

        ctx.try_emit_event("stage.enrichment.completed", {
            "enrichment_keys": list(enrichment_data.keys()),
        })

        return StageOutput.ok(enrichment=enrichment_data)


class ResponseStage:
    """Stage that generates final response."""

    name = "response"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Generate response from prior stage outputs."""
        inputs = ctx.config.get("inputs")

        # Get results from unified_tool stage
        tool_results = []
        enrichment = {}

        if inputs:
            prior = inputs.prior_outputs
            if "unified_tool" in prior:
                tool_results = prior["unified_tool"].data.get("results", [])
            if "enrichment" in prior:
                enrichment = prior["enrichment"].data.get("enrichment", {})

        # Generate response
        successful = [r for r in tool_results if r.get("success")]
        failed = [r for r in tool_results if not r.get("success")]

        response_parts = []
        if successful:
            response_parts.append(f"Successfully executed {len(successful)} action(s)")
        if failed:
            response_parts.append(f"Failed {len(failed)} action(s)")
        if not tool_results:
            response_parts.append("No actions were executed")

        response = ". ".join(response_parts) + "."

        ctx.try_emit_event("stage.response.generated", {
            "response_length": len(response),
            "successful_actions": len(successful),
            "failed_actions": len(failed),
        })

        return StageOutput.ok(
            response=response,
            summary={
                "total_actions": len(tool_results),
                "successful": len(successful),
                "failed": len(failed),
                "enrichment": enrichment,
            },
        )


def create_unified_tools_pipeline():
    """Create the unified tools pipeline."""
    pipeline = Pipeline()
    pipeline = pipeline.with_stage(
        name="enrichment",
        runner=EnrichmentStage,
        kind=StageKind.ENRICH,
    )
    pipeline = pipeline.with_stage(
        name="unified_tool",
        runner=UnifiedToolStage,
        kind=StageKind.TRANSFORM,
        dependencies=("enrichment",),
    )
    pipeline = pipeline.with_stage(
        name="response",
        runner=ResponseStage,
        kind=StageKind.TRANSFORM,
        dependencies=("enrichment", "unified_tool"),
    )
    return pipeline


__all__ = [
    "UnifiedToolStage",
    "EnrichmentStage",
    "ResponseStage",
    "create_unified_tools_pipeline",
    "Action",
]
