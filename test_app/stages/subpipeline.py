"""Subpipeline stage for spawning child pipelines."""

import asyncio

from stageflow import StageContext, StageKind, StageOutput


class SubpipelineStage:
    """Stage that simulates spawning a subpipeline."""

    name = "subpipeline"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Execute subpipeline simulation."""
        inputs = ctx.config.get("inputs")
        if inputs:
            input_text = inputs.snapshot.input_text or ""
            route = inputs.get_from("dispatch", "route", default="agent")
        else:
            input_text = ctx.snapshot.input_text or ""
            route = "agent"

        if route != "subpipeline":
            return StageOutput.skip(
                reason=f"routed_to_{route}",
                data={"route": route},
            )

        await asyncio.sleep(0.2)

        subpipeline_result = {
            "subpipeline_id": f"sub-{id(ctx)}",
            "input": input_text,
            "steps_executed": ["analyze", "process", "summarize"],
            "output": f"Subpipeline processed: {input_text[:50]}...",
        }

        return StageOutput.ok(
            subpipeline_result=subpipeline_result,
            message=f"Executed subpipeline with ID {subpipeline_result['subpipeline_id']}",
            steps_count=len(subpipeline_result["steps_executed"]),
        )


__all__ = ["SubpipelineStage"]
