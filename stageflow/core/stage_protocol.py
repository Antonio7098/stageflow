"""Stage protocol for all stage implementations."""

from typing import Protocol

from .stage_context import StageContext
from .stage_enums import StageKind
from .stage_output import StageOutput


class Stage(Protocol):
    """Protocol for all stage implementations.

    Every component in the framework system is a Stage with a
    StageKind. This includes:
    - STT, TTS, LLM stages (TRANSFORM)
    - Profile, Memory, Skills stages (ENRICH)
    - Router, Dispatcher stages (ROUTE)
    - Guardrails, Policy stages (GUARD)
    - Assessment, Triage, Persist stages (WORK)
    - Coach, Interviewer stages (AGENT)

    Each stage has:
    - name: Unique identifier within its kind
    - kind: StageKind categorization
    - execute(ctx): Core execution method
    """

    name: str
    kind: StageKind

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Execute the stage logic.

        Args:
            ctx: StageContext with snapshot and output buffer

        Returns:
            StageOutput with status, data, artifacts, and events
        """
        ...
