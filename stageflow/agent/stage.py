"""Stage wrapper around the reusable agent runtime."""

from __future__ import annotations

from typing import Any

from stageflow.contracts import TypedStageOutput
from stageflow.core import StageKind, StageOutput

from .runtime import Agent, AgentRunResult


class AgentStage:
    """Stageflow stage that runs a reusable agent loop."""

    name = "agent"
    kind = StageKind.AGENT

    def __init__(self, agent: Agent, *, output_version: str = "agent/stage/v1") -> None:
        self._agent = agent
        self._output = TypedStageOutput(AgentRunResult, default_version=output_version)

    async def execute(self, ctx: Any) -> StageOutput:
        """Execute the agent against the current stage input."""
        try:
            result = await self._agent.run(ctx.snapshot.input_text or "", stage_context=ctx)
            return self._output.ok(result.model_dump())
        except Exception as exc:
            return StageOutput.fail(error=f"Agent execution failed: {exc}")


__all__ = ["AgentStage"]
