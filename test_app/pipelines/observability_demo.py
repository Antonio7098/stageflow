"""Pipeline demonstrating full observability with event emission.

This pipeline showcases:
- Event emission through StageContext.try_emit_event()
- Event sink integration
- Structured logging with correlation IDs
- Multi-stage pipeline with observable execution
"""

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from stageflow import Pipeline, StageContext, StageKind, StageOutput
from stageflow.tools import (
    AdvancedToolExecutor,
    ToolDefinition,
    ToolInput,
    ToolOutput,
    ToolExecutorConfig,
)


@dataclass(frozen=True)
class Action:
    """Action for tool execution."""
    id: UUID
    type: str
    payload: dict[str, Any]


async def compute_handler(input: ToolInput) -> ToolOutput:
    """Compute tool - performs a computation."""
    a = input.payload.get("a", 0)
    b = input.payload.get("b", 0)
    op = input.payload.get("operation", "add")
    
    if op == "add":
        result = a + b
    elif op == "multiply":
        result = a * b
    elif op == "subtract":
        result = a - b
    else:
        return ToolOutput.fail(f"Unknown operation: {op}")
    
    return ToolOutput.ok(data={"result": result, "operation": op, "a": a, "b": b})


async def format_handler(input: ToolInput) -> ToolOutput:
    """Format tool - formats data as string."""
    data = input.payload.get("data", {})
    template = input.payload.get("template", "{data}")
    
    try:
        formatted = template.format(data=data)
        return ToolOutput.ok(data={"formatted": formatted})
    except Exception as e:
        return ToolOutput.fail(f"Format error: {e}")


class InputParserStage:
    """Stage that parses and validates input."""
    
    name = "input_parser"
    kind = StageKind.TRANSFORM
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        """Parse input text into structured data."""
        ctx.try_emit_event("stage.input_parser.started", {
            "stage": self.name,
        })
        
        inputs = ctx.config.get("inputs")
        if inputs:
            input_text = inputs.snapshot.input_text or ""
        else:
            input_text = ctx.snapshot.input_text or ""
        
        # Simulate parsing
        await asyncio.sleep(0.05)
        
        parsed = {
            "raw_input": input_text,
            "word_count": len(input_text.split()),
            "char_count": len(input_text),
            "has_numbers": any(c.isdigit() for c in input_text),
        }
        
        ctx.try_emit_event("stage.input_parser.completed", {
            "stage": self.name,
            "word_count": parsed["word_count"],
            "char_count": parsed["char_count"],
        })
        
        return StageOutput.ok(parsed=parsed)


class ComputeStage:
    """Stage that performs computations using tools."""
    
    name = "compute"
    kind = StageKind.TRANSFORM
    
    def __init__(self):
        self.executor = AdvancedToolExecutor(
            config=ToolExecutorConfig(emit_events=True)
        )
        self.executor.register(ToolDefinition(
            name="compute",
            action_type="COMPUTE",
            handler=compute_handler,
            description="Performs arithmetic computations",
        ))
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        """Execute computations."""
        ctx.try_emit_event("stage.compute.started", {
            "stage": self.name,
        })
        
        # Get parsed input from prior stage
        inputs = ctx.config.get("inputs")
        parsed = {}
        if inputs and "input_parser" in inputs.prior_outputs:
            parsed = inputs.prior_outputs["input_parser"].data.get("parsed", {})
        
        # Perform some computations based on input
        word_count = parsed.get("word_count", 0)
        char_count = parsed.get("char_count", 0)
        
        results = []
        
        # Compute word * char
        action = Action(
            id=uuid4(),
            type="COMPUTE",
            payload={"a": word_count, "b": char_count, "operation": "multiply"},
        )
        
        try:
            output = await self.executor.execute(action, ctx)
            results.append({
                "computation": "word_count * char_count",
                "result": output.data.get("result") if output.success else None,
                "success": output.success,
            })
        except Exception as e:
            results.append({
                "computation": "word_count * char_count",
                "error": str(e),
                "success": False,
            })
        
        # Compute word + char
        action2 = Action(
            id=uuid4(),
            type="COMPUTE",
            payload={"a": word_count, "b": char_count, "operation": "add"},
        )
        
        try:
            output2 = await self.executor.execute(action2, ctx)
            results.append({
                "computation": "word_count + char_count",
                "result": output2.data.get("result") if output2.success else None,
                "success": output2.success,
            })
        except Exception as e:
            results.append({
                "computation": "word_count + char_count",
                "error": str(e),
                "success": False,
            })
        
        ctx.try_emit_event("stage.compute.completed", {
            "stage": self.name,
            "computations_count": len(results),
            "successful_count": sum(1 for r in results if r["success"]),
        })
        
        return StageOutput.ok(
            computations=results,
            input_stats={"word_count": word_count, "char_count": char_count},
        )


class FormatStage:
    """Stage that formats output."""
    
    name = "format"
    kind = StageKind.TRANSFORM
    
    def __init__(self):
        self.executor = AdvancedToolExecutor(
            config=ToolExecutorConfig(emit_events=True)
        )
        self.executor.register(ToolDefinition(
            name="format",
            action_type="FORMAT",
            handler=format_handler,
            description="Formats data as string",
        ))
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        """Format computation results."""
        ctx.try_emit_event("stage.format.started", {
            "stage": self.name,
        })
        
        # Get computation results
        inputs = ctx.config.get("inputs")
        computations = []
        input_stats = {}
        
        if inputs and "compute" in inputs.prior_outputs:
            compute_data = inputs.prior_outputs["compute"].data
            computations = compute_data.get("computations", [])
            input_stats = compute_data.get("input_stats", {})
        
        # Format results
        formatted_lines = []
        formatted_lines.append(f"Input Statistics:")
        formatted_lines.append(f"  - Words: {input_stats.get('word_count', 0)}")
        formatted_lines.append(f"  - Characters: {input_stats.get('char_count', 0)}")
        formatted_lines.append("")
        formatted_lines.append("Computation Results:")
        
        for comp in computations:
            if comp.get("success"):
                formatted_lines.append(f"  - {comp['computation']} = {comp['result']}")
            else:
                formatted_lines.append(f"  - {comp['computation']} = ERROR: {comp.get('error', 'unknown')}")
        
        formatted_output = "\n".join(formatted_lines)
        
        ctx.try_emit_event("stage.format.completed", {
            "stage": self.name,
            "output_length": len(formatted_output),
            "lines_count": len(formatted_lines),
        })
        
        return StageOutput.ok(
            formatted_output=formatted_output,
            summary={
                "total_computations": len(computations),
                "successful": sum(1 for c in computations if c.get("success")),
            },
        )


class AggregatorStage:
    """Final stage that aggregates all results."""
    
    name = "aggregator"
    kind = StageKind.TRANSFORM
    
    async def execute(self, ctx: StageContext) -> StageOutput:
        """Aggregate all stage results."""
        ctx.try_emit_event("stage.aggregator.started", {
            "stage": self.name,
        })
        
        inputs = ctx.config.get("inputs")
        
        # Collect all prior outputs
        aggregated = {
            "stages_executed": [],
            "total_events_emitted": 0,
        }
        
        if inputs:
            for stage_name, output in inputs.prior_outputs.items():
                aggregated["stages_executed"].append({
                    "name": stage_name,
                    "status": output.status.value,
                    "data_keys": list(output.data.keys()),
                })
            
            # Get formatted output
            if "format" in inputs.prior_outputs:
                aggregated["final_output"] = inputs.prior_outputs["format"].data.get("formatted_output", "")
                aggregated["summary"] = inputs.prior_outputs["format"].data.get("summary", {})
        
        ctx.try_emit_event("stage.aggregator.completed", {
            "stage": self.name,
            "stages_aggregated": len(aggregated["stages_executed"]),
        })
        
        return StageOutput.ok(**aggregated)


def create_observability_demo_pipeline():
    """Create the observability demo pipeline."""
    pipeline = Pipeline()
    pipeline = pipeline.with_stage(
        name="input_parser",
        runner=InputParserStage,
        kind=StageKind.TRANSFORM,
    )
    pipeline = pipeline.with_stage(
        name="compute",
        runner=ComputeStage,
        kind=StageKind.TRANSFORM,
        dependencies=("input_parser",),
    )
    pipeline = pipeline.with_stage(
        name="format",
        runner=FormatStage,
        kind=StageKind.TRANSFORM,
        dependencies=("compute",),
    )
    pipeline = pipeline.with_stage(
        name="aggregator",
        runner=AggregatorStage,
        kind=StageKind.TRANSFORM,
        dependencies=("input_parser", "compute", "format"),
    )
    return pipeline


__all__ = [
    "InputParserStage",
    "ComputeStage",
    "FormatStage",
    "AggregatorStage",
    "create_observability_demo_pipeline",
]
