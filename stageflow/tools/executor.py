"""Legacy ToolExecutor stage for executing agent actions.

Note: For new implementations, use AdvancedToolExecutor from executor_v2
which provides behavior gating, undo semantics, and HITL approval.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from .registry import get_tool_registry

if TYPE_CHECKING:
    from stageflow.stages.context import PipelineContext

logger = logging.getLogger("stageflow.tools.executor")


class ActionProtocol(Protocol):
    """Protocol for action objects."""

    @property
    def type(self) -> str:
        ...

    @property
    def payload(self) -> dict[str, Any]:
        ...


class PlanProtocol(Protocol):
    """Protocol for plan objects containing actions."""

    @property
    def actions(self) -> list[ActionProtocol]:
        ...


@dataclass
class ToolExecutorResult:
    """Result from tool execution stage."""

    actions_executed: int = 0
    actions_failed: int = 0
    artifacts_produced: list[dict[str, Any]] = field(default_factory=list)
    requires_reentry: bool = False
    error: str | None = None


class ToolExecutor:
    """Pipeline stage that executes agent actions.

    The ToolExecutor:
    1. Receives a Plan from the agent
    2. For each action in the plan, looks up the corresponding tool
    3. Executes the action through the tool
    4. Collects any artifacts produced
    5. Determines if re-entry is needed (depends on action results)

    Note: For advanced features like behavior gating, undo, and approval,
    use AdvancedToolExecutor instead.
    """

    id = "stage.tool_executor"

    def __init__(self) -> None:
        self.registry = get_tool_registry()

    async def execute(
        self,
        ctx: PipelineContext,
        plan: PlanProtocol | None = None,
    ) -> ToolExecutorResult:
        """Execute all actions in the plan.

        Args:
            ctx: Pipeline context with user, session, etc.
            plan: Plan from the agent containing actions

        Returns:
            ToolExecutorResult with execution results and artifacts
        """
        if plan is None:
            return ToolExecutorResult()

        result = ToolExecutorResult()

        for action in plan.actions:
            try:
                output = await self.registry.execute(action, ctx.to_dict())

                if output is None:
                    result.actions_failed += 1
                    logger.warning(f"No tool available for action type: {action.type}")
                    continue

                if output.success:
                    result.actions_executed += 1

                    # Collect artifacts from tool output
                    if output.artifacts:
                        result.artifacts_produced.extend(output.artifacts)

                    # Check if action requires re-entry
                    if action.payload.get("requires_reentry"):
                        result.requires_reentry = True
                else:
                    result.actions_failed += 1
                    logger.error(f"Action {action.type} failed: {output.error}")

            except Exception as e:
                result.actions_failed += 1
                logger.error(
                    f"Error executing action {action.type}: {e}",
                    exc_info=True,
                )

        # Determine if re-entry is needed based on failed actions
        if result.actions_failed > 0:
            result.requires_reentry = True

        return result


__all__ = ["ToolExecutor", "ToolExecutorResult"]
