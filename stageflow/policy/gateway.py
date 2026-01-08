import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import func, select

from app.config import get_settings
from app.database import get_session_context
from app.models import OrganizationMembership
from app.models.observability import PipelineRun

if TYPE_CHECKING:
    pass

logger = logging.getLogger("policy")


def _get_pipeline_event_logger(db):
    """Lazy import of PipelineEventLogger to avoid circular import."""
    from app.ai.framework.observability import PipelineEventLogger

    return PipelineEventLogger(db)


class PolicyCheckpoint(str, Enum):
    PRE_LLM = "pre_llm"
    POST_LLM = "post_llm"
    PRE_ACTION = "pre_action"
    PRE_PERSIST = "pre_persist"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(frozen=True)
class PolicyContext:
    pipeline_run_id: UUID
    request_id: UUID | None
    session_id: UUID | None
    user_id: UUID | None
    org_id: UUID | None
    service: str
    trigger: str | None
    behavior: str | None  # Coaching style: practice, roleplay, etc.
    quality_mode: str | None  # Performance mode: fast, accurate (derived from topology)
    intent: str | None
    prompt_tokens_estimate: int | None = None
    proposed_action_types: list[str] | None = None
    proposed_artifact_types: list[str] | None = None


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    reason: str
    details: dict[str, Any] | None = None


class PolicyGateway:
    def _get_intent_rules(self, raw_rules: str) -> dict[str, Any]:
        if not raw_rules:
            return {}
        try:
            parsed = json.loads(raw_rules)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    async def evaluate(
        self,
        *,
        checkpoint: PolicyCheckpoint,
        context: PolicyContext,
    ) -> PolicyResult:
        settings = get_settings()

        membership_details: dict[str, Any] | None = None
        if not getattr(settings, "policy_gateway_enabled", True):
            result = PolicyResult(decision=PolicyDecision.ALLOW, reason="disabled")
            await self._emit_decision(checkpoint=checkpoint, context=context, result=result)
            return result
        # Defer tenant membership checks until after specific policy checks so those reasons take precedence
        tenant_required = getattr(settings, "workos_auth_enabled", False)

        forced_checkpoint = getattr(settings, "policy_force_checkpoint", None)
        forced_decision = getattr(settings, "policy_force_decision", None)
        logger.info(
            f"[DEBUG] PolicyGateway: forced_checkpoint={forced_checkpoint}, forced_decision={forced_decision}, checkpoint={checkpoint.value}"
        )
        logger.info(
            f"[DEBUG] PolicyGateway: settings.policy_force_checkpoint={getattr(settings, 'policy_force_checkpoint', 'NOT_SET')}"
        )
        logger.info(
            f"[DEBUG] PolicyGateway: settings.policy_force_decision={getattr(settings, 'policy_force_decision', 'NOT_SET')}"
        )
        if forced_checkpoint and forced_decision and str(forced_checkpoint) == checkpoint.value:
            reason = getattr(settings, "policy_force_reason", None) or "forced"
            try:
                decision = PolicyDecision(str(forced_decision))
            except Exception:
                decision = PolicyDecision.BLOCK
            result = PolicyResult(decision=decision, reason=reason)
            await self._emit_decision(checkpoint=checkpoint, context=context, result=result)
            return result

        if getattr(settings, "policy_allowlist_enabled", True):
            allowlist_value = None
            if checkpoint == PolicyCheckpoint.PRE_LLM:
                allowlist_value = getattr(settings, "policy_allowlist_pre_llm", "")
            elif checkpoint == PolicyCheckpoint.PRE_ACTION:
                allowlist_value = getattr(settings, "policy_allowlist_pre_action", "")
            elif checkpoint == PolicyCheckpoint.PRE_PERSIST:
                allowlist_value = getattr(settings, "policy_allowlist_pre_persist", "")

            allowed_intents = {
                item.strip() for item in (allowlist_value or "").split(",") if item.strip()
            }
            if allowed_intents:
                intent = (context.intent or "").strip()
                if intent not in allowed_intents:
                    result = PolicyResult(
                        decision=PolicyDecision.BLOCK,
                        reason="intent_not_allowed",
                        details={
                            "intent": intent,
                            "allowed": sorted(allowed_intents),
                        },
                    )
                    if membership_details is not None:
                        result = PolicyResult(
                            decision=result.decision,
                            reason=result.reason,
                            details={**(result.details or {}), "membership": membership_details},
                        )
                    await self._emit_decision(checkpoint=checkpoint, context=context, result=result)
                    return result

        intent = (context.intent or "").strip()
        intent_rules = self._get_intent_rules(
            getattr(settings, "policy_intent_rules_json", "") or ""
        )
        rules_for_intent: dict[str, Any] = (
            intent_rules.get(intent) if isinstance(intent_rules.get(intent), dict) else {}
        )

        if checkpoint == PolicyCheckpoint.PRE_ACTION and context.proposed_action_types:
            allowed_raw = rules_for_intent.get("action_types")
            allowed: set[str] = (
                {str(x) for x in allowed_raw} if isinstance(allowed_raw, list) else set()
            )
            proposed = [str(t) for t in context.proposed_action_types if str(t)]
            proposed_set = set(proposed)
            allow_all = "*" in allowed
            denied = [] if allow_all else sorted([t for t in proposed_set if t not in allowed])
            if denied:
                result = PolicyResult(
                    decision=PolicyDecision.BLOCK,
                    reason="escalation.action_type_not_allowed",
                    details={
                        "intent": intent,
                        "proposed": sorted(proposed_set),
                        "allowed": sorted(allowed),
                        "denied": denied,
                    },
                )
                if membership_details is not None:
                    result = PolicyResult(
                        decision=result.decision,
                        reason=result.reason,
                        details={**(result.details or {}), "membership": membership_details},
                    )
                await self._emit_decision(checkpoint=checkpoint, context=context, result=result)
                return result

        if checkpoint == PolicyCheckpoint.PRE_PERSIST and context.proposed_artifact_types:
            allowed_raw = rules_for_intent.get("artifact_types")
            allowed: set[str] = (
                {str(x) for x in allowed_raw} if isinstance(allowed_raw, list) else set()
            )
            proposed = [str(t) for t in context.proposed_artifact_types if str(t)]
            proposed_set = set(proposed)
            allow_all = "*" in allowed
            denied = [] if allow_all else sorted([t for t in proposed_set if t not in allowed])
            if denied:
                result = PolicyResult(
                    decision=PolicyDecision.BLOCK,
                    reason="escalation.artifact_type_not_allowed",
                    details={
                        "intent": intent,
                        "proposed": sorted(proposed_set),
                        "allowed": sorted(allowed),
                        "denied": denied,
                    },
                )
                if membership_details is not None:
                    result = PolicyResult(
                        decision=result.decision,
                        reason=result.reason,
                        details={**(result.details or {}), "membership": membership_details},
                    )
                await self._emit_decision(checkpoint=checkpoint, context=context, result=result)
                return result

        if checkpoint == PolicyCheckpoint.PRE_LLM:
            max_prompt_tokens = getattr(settings, "policy_max_prompt_tokens", None)
            if (
                isinstance(max_prompt_tokens, int)
                and max_prompt_tokens > 0
                and isinstance(context.prompt_tokens_estimate, int)
                and context.prompt_tokens_estimate > max_prompt_tokens
            ):
                result = PolicyResult(
                    decision=PolicyDecision.BLOCK,
                    reason="budget.prompt_tokens_exceeded",
                    details={
                        "prompt_tokens_estimate": context.prompt_tokens_estimate,
                        "max_prompt_tokens": max_prompt_tokens,
                    },
                )
                if membership_details is not None:
                    result = PolicyResult(
                        decision=result.decision,
                        reason=result.reason,
                        details={**(result.details or {}), "membership": membership_details},
                    )
                await self._emit_decision(checkpoint=checkpoint, context=context, result=result)
                return result

            max_runs_per_minute = getattr(settings, "policy_max_runs_per_minute", None)
            if (
                isinstance(max_runs_per_minute, int)
                and max_runs_per_minute > 0
                and context.user_id is not None
            ):
                cutoff = datetime.utcnow() - timedelta(seconds=60)
                async with get_session_context() as db:
                    count_result = await db.execute(
                        select(func.count(PipelineRun.id)).where(
                            PipelineRun.user_id == context.user_id,
                            PipelineRun.created_at >= cutoff,
                            PipelineRun.id != context.pipeline_run_id,
                        )
                    )
                    recent_runs = int(count_result.scalar_one() or 0)
                if recent_runs >= max_runs_per_minute:
                    result = PolicyResult(
                        decision=PolicyDecision.BLOCK,
                        reason="quota.runs_per_minute_exceeded",
                        details={
                            "recent_runs": recent_runs,
                            "max_runs_per_minute": max_runs_per_minute,
                        },
                    )
                    if membership_details is not None:
                        result = PolicyResult(
                            decision=result.decision,
                            reason=result.reason,
                            details={**(result.details or {}), "membership": membership_details},
                        )
                    await self._emit_decision(checkpoint=checkpoint, context=context, result=result)
                    return result

        # Perform tenant checks just before final allow to avoid overshadowing specific denials
        if tenant_required:
            if context.org_id is None:
                result = PolicyResult(decision=PolicyDecision.BLOCK, reason="missing_org_id")
                await self._emit_decision(checkpoint=checkpoint, context=context, result=result)
                return result
            if context.user_id is None:
                result = PolicyResult(decision=PolicyDecision.BLOCK, reason="missing_user_id")
                await self._emit_decision(checkpoint=checkpoint, context=context, result=result)
                return result

            async with get_session_context() as db:
                membership_result = await db.execute(
                    select(OrganizationMembership).where(
                        OrganizationMembership.user_id == context.user_id,
                        OrganizationMembership.organization_id == context.org_id,
                    )
                )
                membership = membership_result.scalar_one_or_none()

            if membership is None:
                result = PolicyResult(
                    decision=PolicyDecision.BLOCK,
                    reason="org_membership_missing",
                    details={
                        "organization_id": str(context.org_id),
                        "user_id": str(context.user_id),
                    },
                )
                await self._emit_decision(checkpoint=checkpoint, context=context, result=result)
                return result

            membership_details = {
                "organization_id": str(context.org_id),
                "role": membership.role,
                "permissions": membership.permissions,
            }

        allow_details = membership_details
        result = PolicyResult(
            decision=PolicyDecision.ALLOW,
            reason="default_allow",
            details=({"membership": allow_details} if allow_details is not None else None),
        )
        await self._emit_decision(checkpoint=checkpoint, context=context, result=result)
        return result

    async def _emit_decision(
        self,
        *,
        checkpoint: PolicyCheckpoint,
        context: PolicyContext,
        result: PolicyResult,
    ) -> None:
        data: dict[str, Any] = {
            "checkpoint": checkpoint.value,
            "decision": result.decision.value,
            "reason": result.reason,
            "details": result.details,
            "service": context.service,
            "trigger": context.trigger,
            "behavior": context.behavior,
            "quality_mode": context.quality_mode,
            "intent": context.intent,
        }

        async with get_session_context() as db:
            event_logger = _get_pipeline_event_logger(db)
            await event_logger.emit(
                pipeline_run_id=context.pipeline_run_id,
                type="policy.decision",
                request_id=context.request_id,
                session_id=context.session_id,
                user_id=context.user_id,
                org_id=context.org_id,
                data=data,
            )

            extra_event_type: str | None = None
            if result.decision != PolicyDecision.ALLOW:
                if result.reason.startswith("budget."):
                    extra_event_type = "policy.budget.exceeded"
                elif result.reason.startswith("quota."):
                    extra_event_type = "policy.quota.exceeded"
                elif result.reason.startswith("escalation."):
                    extra_event_type = "policy.escalation.denied"
                elif result.reason == "intent_not_allowed":
                    extra_event_type = "policy.intent.denied"
                elif result.reason in (
                    "missing_org_id",
                    "missing_user_id",
                    "org_membership_missing",
                ):
                    extra_event_type = "policy.tenant.denied"

            if extra_event_type is not None:
                await event_logger.emit(
                    pipeline_run_id=context.pipeline_run_id,
                    type=extra_event_type,
                    request_id=context.request_id,
                    session_id=context.session_id,
                    user_id=context.user_id,
                    org_id=context.org_id,
                    data=data,
                )

        logger.info(
            "Policy decision",
            extra={
                "service": "policy",
                "pipeline_run_id": str(context.pipeline_run_id),
                "metadata": data,
            },
        )


__all__ = [
    "PolicyCheckpoint",
    "PolicyDecision",
    "PolicyContext",
    "PolicyResult",
    "PolicyGateway",
]
