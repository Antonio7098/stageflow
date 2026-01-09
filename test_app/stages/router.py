"""Router stage for testing routing decisions."""

import asyncio

from stageflow import StageContext, StageKind, StageOutput


class RouterStage:
    """Stage that routes to different paths based on input."""

    name = "router"
    kind = StageKind.ROUTE

    ROUTE_KEYWORDS = {
        "help": "help_flow",
        "code": "code_flow",
        "explain": "explain_flow",
    }

    async def execute(self, ctx: StageContext) -> StageOutput:
        await asyncio.sleep(0.1)

        inputs = ctx.config.get("inputs")
        if inputs:
            input_text = (inputs.snapshot.input_text or "").lower()
        else:
            input_text = (ctx.snapshot.input_text or "").lower()

        route = "default_flow"
        for keyword, flow in self.ROUTE_KEYWORDS.items():
            if keyword in input_text:
                route = flow
                break

        return StageOutput.ok(
            route=route,
            routing_decision={
                "selected_route": route,
                "reason": f"Matched keyword or default",
            },
        )
