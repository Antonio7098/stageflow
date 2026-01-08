"""Guardrails policy stage for content moderation."""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

from app.ai.framework.observability import PipelineEventLogger
from app.config import get_settings
from app.database import get_session_context

logger = logging.getLogger("guardrails")


class GuardrailsCheckpoint(str, Enum):
    PRE_LLM = "pre_llm"
    PRE_ACTION = "pre_action"
    PRE_PERSIST = "pre_persist"


class GuardrailsDecision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"


@dataclass(frozen=True)
class GuardrailsContext:
    pipeline_run_id: UUID
    request_id: UUID
    service: str
    topology: str
    behavior: str
    messages: list[dict[str, Any]]
    checkpoint: GuardrailsCheckpoint
    session_id: UUID | None = None
    user_id: UUID | None = None
    org_id: UUID | None = None


class GuardrailsResult:
    def __init__(
        self,
        decision: GuardrailsDecision,
        reason: str,
        checkpoint: GuardrailsCheckpoint,
        modified_content: list[dict[str, Any]] | None = None,
    ):
        self.decision = decision
        self.reason = reason
        self.checkpoint = checkpoint
        self.modified_content = modified_content or []

    @property
    def should_block(self) -> bool:
        return self.decision == GuardrailsDecision.BLOCK


class GuardrailsStage:
    """Apply content moderation guardrails at specified checkpoints."""

    name = "guardrails"
    kind = "GUARD"

    def __init__(self, checkpoint: GuardrailsCheckpoint):
        self.checkpoint = checkpoint
        self.settings = get_settings()

    async def execute(self, ctx) -> dict:
        """Execute guardrails check."""
        checkpoint_name = self.checkpoint.value

        # Get guardrails for this checkpoint
        guardrails = []
        try:
            from app.ai.framework.policy.guardrails_registry import get_guardrails

            guardrails = get_guardrails(self.checkpoint)
        except Exception as e:
            logger.warning(
                f"No guardrails found for checkpoint {checkpoint_name}",
                extra={"checkpoint": checkpoint_name, "error": str(e)},
            )
            # Return ALLOW result with empty modifications
            return {
                "status": "completed",
                "data": {
                    "guardrails_result": GuardrailsResult(
                        decision=GuardrailsDecision.ALLOW,
                        reason="No guardrails configured",
                        checkpoint=self.checkpoint,
                        modified_content=None,
                    )
                },
            }

        # Apply each guardrail in sequence
        modified_messages = []
        blocked_reasons = []
        for guardrail in guardrails:
            try:
                async with get_session_context() as db:
                    event_logger = PipelineEventLogger(db)
                    result = await guardrail.apply(ctx, event_logger)
                    if result.should_block:
                        blocked_reasons.append(result.reason)
                    elif result.modified_content:
                        modified_messages.extend(result.modified_content)
                    # Log guardrail decision
                    await event_logger.emit(
                        pipeline_run_id=ctx.pipeline_run_id,
                        type=f"guardrails.{checkpoint_name}",
                        request_id=ctx.request_id,
                        session_id=ctx.session_id,
                        user_id=ctx.user_id,
                        org_id=ctx.org_id,
                        data={
                            "checkpoint": checkpoint_name,
                            "guardrail": guardrail.name,
                            "decision": result.decision.value,
                            "reason": result.reason,
                        },
                    )
            except Exception as e:
                logger.exception(
                    f"Guardrail {guardrail.name} failed",
                    extra={
                        "checkpoint": checkpoint_name,
                        "guardrail": guardrail.name,
                        "error": str(e),
                    },
                )
                # Continue with next guardrail

        # Final decision
        if blocked_reasons:
            final_decision = GuardrailsDecision.BLOCK
            final_reason = "; ".join(blocked_reasons)
        elif modified_messages:
            final_decision = GuardrailsDecision.ALLOW
            final_reason = "Content modified by guardrails"
        else:
            final_decision = GuardrailsDecision.ALLOW
            final_reason = "Content passed all guardrails"

        return {
            "status": "completed",
            "data": {
                "guardrails_result": GuardrailsResult(
                    decision=final_decision,
                    reason=final_reason,
                    checkpoint=self.checkpoint,
                    modified_content=modified_messages if modified_messages else None,
                )
            },
        }
