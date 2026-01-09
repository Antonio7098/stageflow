"""Guard stages for testing guardrails."""

from stageflow import StageContext, StageKind, StageOutput

from services.mocks import MockGuardService


class InputGuardStage:
    """Guard stage that validates input."""

    name = "input_guard"
    kind = StageKind.GUARD

    def __init__(self, guard_service: MockGuardService | None = None):
        self.guard_service = guard_service or MockGuardService()

    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs = ctx.config.get("inputs")
        if inputs:
            input_text = inputs.snapshot.input_text or ""
        else:
            input_text = ctx.snapshot.input_text or ""

        is_safe, reason = await self.guard_service.check_input(input_text)

        if not is_safe:
            return StageOutput.cancel(
                reason=f"Input blocked: {reason}",
                data={"blocked": True, "reason": reason},
            )

        return StageOutput.ok(
            validated=True,
            text=input_text,
        )


class OutputGuardStage:
    """Guard stage that validates output."""

    name = "output_guard"
    kind = StageKind.GUARD

    def __init__(self, guard_service: MockGuardService | None = None):
        self.guard_service = guard_service or MockGuardService()

    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs = ctx.config.get("inputs")
        if inputs:
            response = inputs.get("response", "")
        else:
            response = ""

        is_safe, reason = await self.guard_service.check_output(response)

        if not is_safe:
            return StageOutput.ok(
                response="I apologize, but I cannot provide that response.",
                filtered=True,
                reason=reason,
            )

        return StageOutput.ok(
            response=response,
            validated=True,
        )
