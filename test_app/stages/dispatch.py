"""Dispatch stage for routing to agent or subpipeline."""

import asyncio

from stageflow import StageContext, StageKind, StageOutput


class DispatchStage:
    """Stage that routes to agent or subpipeline based on input."""

    name = "dispatch"
    kind = StageKind.ROUTE

    SUBPIPELINE_KEYWORDS = ["subpipeline", "spawn", "child", "nested", "delegate"]

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Execute routing decision."""
        inputs = ctx.config.get("inputs")
        input_text = inputs.snapshot.input_text or "" if inputs else ctx.snapshot.input_text or ""

        await asyncio.sleep(0.1)

        lower_text = input_text.lower()
        route = "agent"

        for keyword in self.SUBPIPELINE_KEYWORDS:
            if keyword in lower_text:
                route = "subpipeline"
                break

        return StageOutput.ok(
            route=route,
            routing_decision={
                "selected_route": route,
                "reason": "Matched keyword or defaulted to agent",
            },
        )


__all__ = ["DispatchStage"]
