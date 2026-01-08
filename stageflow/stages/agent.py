"""Agent types and tool execution for substrate architecture.

This module provides:
- Action: Typed request for a capability/tool
- ActionType: Type alias for action type strings
- AgentResult: Result wrapper for tool execution
- ToolExecutor: Executes actions using registered tools
- handle_agent_output_runtime: Process agent output with policy checks

The tool system integrates with the unified Stage protocol:
- Agent stages return StageOutput with actions in data["actions"]
- Actions are executed by ToolExecutor
- Results are returned as AgentResult
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.ai.framework.observability import PipelineEventLogger
from app.ai.framework.policy.gateway import (
    PolicyCheckpoint,
    PolicyContext,
    PolicyDecision,
    PolicyGateway,
)
from app.config import get_settings
from app.models import Artifact
from app.schemas.agent_output import AgentOutput

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.ai.framework.core.stages import StageContext


logger = logging.getLogger(__name__)


# =============================================================================
# Action Types
# =============================================================================

ActionType = str
"""Type alias for action type strings.

Action types are managed by the ToolRegistry - tools register themselves
with their supported action types at runtime. This provides full extensibility
without hardcoded enums.

Common action types:
- "update_profile" - Update user profile fields
- "edit_document" - Edit a document or script
- "store_memory" - Store a fact in user memory
- "switch_topology" - Change pipeline topology
- "provide_feedback" - Provide structured feedback
- "run_assessment" - Trigger assessment flow
"""


@dataclass(frozen=True)
class Action:
    """Typed request for a capability/tool.

    Actions are the mechanism by which agents request work to be done.
    They are NOT executed directly by the agent - instead, they are
    passed to the ToolExecutor for processing.
    """

    type: ActionType
    payload: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    skill_id: str | None = None
    undo_available: bool = False


@dataclass
class AgentResult:
    """Result of agent/tool action execution."""

    success: bool
    action_type: str
    result_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    approval_required: bool = False
    approval_granted: bool = False


# =============================================================================
# Tool Registry
# =============================================================================

if TYPE_CHECKING:
    from typing import Protocol

    class ToolHandler(Protocol):
        """Protocol for tool handlers."""

        async def __call__(self, action: Action, context: StageContext) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ToolRegistration:
    """Registration information for a tool."""

    name: str
    handler: Any  # ToolHandler
    requires_approval: bool = False
    description: str = ""


class ToolRegistry:
    """Registry for available tools keyed by action type."""

    _registry: dict[str, ToolRegistration] = {}

    @classmethod
    def register(
        cls,
        action_type: str,
        *,
        name: str = "",
        requires_approval: bool = False,
        description: str = "",
    ) -> Any:
        """Decorator to register a tool handler for an action type."""

        def decorator(handler: Any) -> Any:
            registration = ToolRegistration(
                name=name or handler.__name__,
                handler=handler,
                requires_approval=requires_approval,
                description=description,
            )
            cls._registry[action_type] = registration
            return handler

        return decorator

    @classmethod
    def get(cls, action_type: str) -> ToolRegistration | None:
        """Get tool registration for an action type."""
        return cls._registry.get(action_type)

    @classmethod
    def get_or_raise(cls, action_type: str) -> ToolRegistration:
        """Get tool registration or raise KeyError."""
        reg = cls._registry.get(action_type)
        if reg is None:
            available = list(cls._registry.keys())
            raise KeyError(
                f"No tool registered for action type '{action_type}'. Available: {available}"
            )
        return reg

    @classmethod
    def has(cls, action_type: str) -> bool:
        """Check if a tool is registered."""
        return action_type in cls._registry

    @classmethod
    def list_types(cls) -> list[str]:
        """List all registered action types."""
        return list(cls._registry.keys())

    @classmethod
    def get_all(cls) -> dict[str, ToolRegistration]:
        """Get all registrations."""
        return cls._registry.copy()

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations (testing only)."""
        cls._registry.clear()


# =============================================================================
# Tool Executor
# =============================================================================


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""

    def __init__(self, action_type: str, reason: str, original: Exception | None = None):
        self.action_type = action_type
        self.reason = reason
        self.original = original
        super().__init__(f"Tool execution failed for '{action_type}': {reason}")


class ToolNotFoundError(Exception):
    """Raised when no tool is registered for an action type."""

    def __init__(self, action_type: str):
        self.action_type = action_type
        available = ToolRegistry.list_types()
        super().__init__(
            f"No tool registered for action type: '{action_type}'. Available: {available}"
        )


class ToolExecutor:
    """Executes actions using registered tools.

    This class provides an interface between agent-produced Actions
    and concrete tool implementations registered via ToolRegistry.
    """

    def __init__(self, strict: bool = False) -> None:
        """Initialize the tool executor.

        Args:
            strict: If True, raises ToolNotFoundError for unknown action types.
                    If False, returns empty dict for unknown actions.
        """
        self.strict = strict

    async def execute(
        self,
        action: Action,
        context: StageContext,
    ) -> AgentResult:
        """Execute an action using its registered tool.

        Args:
            action: The Action to execute
            context: StageContext for accessing snapshot, ports, etc.

        Returns:
            AgentResult containing success status and result data
        """
        action_type = action.type

        # Look up the tool for this action type
        tool = ToolRegistry.get(action_type)

        if tool is None:
            if self.strict:
                raise ToolNotFoundError(action_type)
            else:
                logger.warning(
                    f"No tool registered for action type '{action_type}'. Returning empty result."
                )
                return AgentResult(
                    success=False,
                    action_type=action_type,
                    error="No tool registered",
                )

        # Check if approval is required
        if tool.requires_approval and action.requires_approval:
            return AgentResult(
                success=False,
                action_type=action_type,
                approval_required=True,
                error="Approval required",
            )

        # Execute the tool
        try:
            logger.info(
                f"Executing tool '{tool.name}' for action '{action_type}'",
                extra={
                    "action_type": action_type,
                    "tool_name": tool.name,
                    "requires_approval": tool.requires_approval,
                },
            )

            result = await tool.handler(action, context)

            # Validate result is a dict
            if not isinstance(result, dict):
                logger.error(f"Tool '{tool.name}' returned non-dict result: {type(result)}")
                return AgentResult(
                    success=False,
                    action_type=action_type,
                    error=f"Invalid tool result type: {type(result)}",
                )

            logger.debug(
                f"Tool '{tool.name}' completed successfully",
                extra={"action_type": action_type, "tool_name": tool.name},
            )

            return AgentResult(
                success=True,
                action_type=action_type,
                result_data=result,
            )

        except Exception as e:
            logger.exception(
                f"Tool '{tool.name}' failed for action '{action_type}'",
                extra={
                    "action_type": action_type,
                    "tool_name": tool.name,
                    "error": str(e),
                },
            )
            raise ToolExecutionError(
                action_type=action_type,
                reason=f"Tool handler raised exception: {str(e)}",
                original=e,
            ) from e

    async def execute_batch(
        self,
        actions: list[Action],
        context: StageContext,
    ) -> list[AgentResult]:
        """Execute multiple actions in parallel.

        Args:
            actions: List of Actions to execute
            context: StageContext for execution

        Returns:
            List of AgentResult (one per action)
        """
        import asyncio

        if not actions:
            return []

        # Execute all actions in parallel
        results = await asyncio.gather(
            *[self.execute(action, context) for action in actions],
            return_exceptions=True,
        )

        # Convert exceptions to AgentResult
        return [
            r
            if isinstance(r, AgentResult)
            else AgentResult(
                success=False,
                action_type=getattr(r, "action_type", "unknown"),
                error=str(r),
            )
            for r in results
        ]

    def can_execute(self, action_type: str) -> bool:
        """Check if a tool is registered for an action type."""
        return ToolRegistry.has(action_type)

    def get_registered_tools(self) -> dict[str, str]:
        """Get mapping of action types to tool names."""
        tools = ToolRegistry.get_all()
        return {action_type: tool.name for action_type, tool in tools.items()}


# =============================================================================
# Convenience Functions
# =============================================================================


def execute_action(action: Action, context: StageContext) -> AgentResult:
    """Convenience function to execute a single action."""
    executor = ToolExecutor()
    import asyncio

    return asyncio.run(executor.execute(action, context))


def execute_actions(actions: list[Action], context: StageContext) -> list[AgentResult]:
    """Convenience function to execute multiple actions."""
    executor = ToolExecutor()
    import asyncio

    return asyncio.run(executor.execute_batch(actions, context))


# =============================================================================
# Agent Output Runtime Handler
# =============================================================================


async def handle_agent_output_runtime(
    *,
    db: AsyncSession,
    agent_output: AgentOutput,
    pipeline_run_id: UUID | None,
    request_id: UUID | None,
    session_id: UUID | None,
    user_id: UUID | None,
    org_id: UUID | None,
    service: str,
) -> None:
    """Process agent output with policy checks and artifact persistence.

    This function handles the runtime processing of agent outputs, including:
    - Policy evaluation for actions
    - Policy evaluation for artifacts
    - Artifact persistence to the database

    Args:
        db: Database session
        agent_output: The agent output to process
        pipeline_run_id: Pipeline run identifier
        request_id: Request identifier
        session_id: Session identifier
        user_id: User identifier
        org_id: Organization identifier
        service: High-level service name (e.g., "chat", "voice")
    """
    if pipeline_run_id is None:
        return

    event_logger = PipelineEventLogger(db)
    gateway = PolicyGateway()

    high_level_intent = service

    if agent_output.actions:
        await event_logger.emit(
            pipeline_run_id=pipeline_run_id,
            type="agent_output.actions.present",
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
            data={
                "count": len(agent_output.actions),
                "types": [a.type for a in agent_output.actions],
            },
        )
        pre_action_ctx = PolicyContext(
            pipeline_run_id=pipeline_run_id,
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
            service=service,
            trigger=None,
            behavior=None,
            quality_mode=None,
            intent=high_level_intent,
            proposed_action_types=[a.type for a in agent_output.actions],
        )
        pre_action = await gateway.evaluate(
            checkpoint=PolicyCheckpoint.PRE_ACTION,
            context=pre_action_ctx,
        )
        if pre_action.decision != PolicyDecision.ALLOW:
            await event_logger.emit(
                pipeline_run_id=pipeline_run_id,
                type="agent_output.actions.denied",
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
                data={
                    "reason": pre_action.reason,
                    "decision": pre_action.decision.value,
                },
            )
            return

        await event_logger.emit(
            pipeline_run_id=pipeline_run_id,
            type="agent_output.actions.skipped",
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
            data={
                "reason": "executor_not_implemented",
                "count": len(agent_output.actions),
                "types": [a.type for a in agent_output.actions],
            },
        )

    if not agent_output.artifacts:
        return

    settings = get_settings()
    max_artifacts = getattr(settings, "policy_max_artifacts", None)
    if (
        isinstance(max_artifacts, int)
        and max_artifacts > 0
        and len(agent_output.artifacts) > max_artifacts
    ):
        await event_logger.emit(
            pipeline_run_id=pipeline_run_id,
            type="agent_output.artifacts.rejected",
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
            data={
                "reason": "max_artifacts_exceeded",
                "count": len(agent_output.artifacts),
                "max_artifacts": max_artifacts,
            },
        )
        return

    max_payload_bytes = getattr(settings, "policy_max_artifact_payload_bytes", None)
    if isinstance(max_payload_bytes, int) and max_payload_bytes > 0:
        for artifact in agent_output.artifacts:
            try:
                payload_bytes = len(
                    json.dumps(artifact.payload, separators=(",", ":"), ensure_ascii=False).encode(
                        "utf-8"
                    )
                )
            except Exception as exc:
                logger.error(
                    f"Failed to calculate payload bytes for artifact {artifact.type}: {exc}",
                    exc_info=True,
                )
                payload_bytes = None
            if payload_bytes is not None and payload_bytes > max_payload_bytes:
                await event_logger.emit(
                    pipeline_run_id=pipeline_run_id,
                    type="agent_output.artifacts.rejected",
                    request_id=request_id,
                    session_id=session_id,
                    user_id=user_id,
                    org_id=org_id,
                    data={
                        "reason": "max_artifact_payload_bytes_exceeded",
                        "artifact_type": artifact.type,
                        "payload_bytes": payload_bytes,
                        "max_payload_bytes": max_payload_bytes,
                    },
                )
                return

    await event_logger.emit(
        pipeline_run_id=pipeline_run_id,
        type="agent_output.artifacts.present",
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        org_id=org_id,
        data={
            "count": len(agent_output.artifacts),
            "types": [a.type for a in agent_output.artifacts],
        },
    )

    pre_persist_ctx = PolicyContext(
        pipeline_run_id=pipeline_run_id,
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        org_id=org_id,
        service=service,
        trigger=None,
        behavior=None,
        quality_mode=None,
        intent=high_level_intent,
        proposed_artifact_types=[a.type for a in agent_output.artifacts],
    )
    pre_persist = await gateway.evaluate(
        checkpoint=PolicyCheckpoint.PRE_PERSIST,
        context=pre_persist_ctx,
    )
    if pre_persist.decision != PolicyDecision.ALLOW:
        await event_logger.emit(
            pipeline_run_id=pipeline_run_id,
            type="agent_output.artifacts.denied",
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
            data={
                "reason": pre_persist.reason,
                "decision": pre_persist.decision.value,
            },
        )
        return

    for artifact in agent_output.artifacts:
        db.add(
            Artifact(
                pipeline_run_id=pipeline_run_id,
                type=artifact.type,
                payload=artifact.payload,
                session_id=session_id,
                user_id=user_id,
                org_id=org_id,
            )
        )

    await event_logger.emit(
        pipeline_run_id=pipeline_run_id,
        type="agent_output.artifacts.persisted",
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        org_id=org_id,
        data={
            "count": len(agent_output.artifacts),
            "types": [a.type for a in agent_output.artifacts],
        },
    )


__all__ = [
    # Types
    "Action",
    "ActionType",
    "AgentResult",
    # Registry
    "ToolRegistry",
    "ToolRegistration",
    # Executor
    "ToolExecutor",
    "ToolExecutionError",
    "ToolNotFoundError",
    # Convenience
    "execute_action",
    "execute_actions",
    # Runtime handler
    "handle_agent_output_runtime",
]
