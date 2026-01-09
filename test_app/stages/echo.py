"""Simple echo stage for testing basic execution."""

import asyncio

from stageflow import StageContext, StageKind, StageOutput


class EchoStage:
    """Simple stage that echoes the input text."""

    name = "echo"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        await asyncio.sleep(0.2)

        inputs = ctx.config.get("inputs")
        input_text = inputs.snapshot.input_text or "" if inputs else ctx.snapshot.input_text or ""

        return StageOutput.ok(
            echo=input_text,
            message=f"Echoed: {input_text}",
        )
