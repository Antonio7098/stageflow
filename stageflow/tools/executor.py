"""ToolExecutor stage for executing agent actions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.ai.framework.agent.types import Artifact, ArtifactType, Plan
from app.ai.framework.pipeline import PipelineContext, Stage, StageResult
from app.ai.framework.tools.registry import get_tool_registry

logger = logging.getLogger("tool_executor")


@dataclass
class ToolExecutorResult:
    """Result from tool execution stage."""

    actions_executed: int = 0
    actions_failed: int = 0
    artifacts_produced: list[Artifact] = field(default_factory=list)
    requires_reentry: bool = False
    error: str | None = None


class ToolExecutor(Stage):
    """Pipeline stage that executes agent actions.

    The ToolExecutor:
    1. Receives a Plan from the agent
    2. For each action in the plan, looks up the corresponding tool
    3. Executes the action through the tool
    4. Collects any artifacts produced
    5. Determines if re-entry is needed (depends on action results)
    """

    id = "stage.tool_executor"

    def __init__(self) -> None:
        self.registry = get_tool_registry()

    async def execute(
        self,
        ctx: PipelineContext,
        input: Plan | None = None,
    ) -> ToolExecutorResult:
        """Execute all actions in the plan.

        Args:
            ctx: Pipeline context with user, session, etc.
            input: Plan from the agent containing actions

        Returns:
            ToolExecutorResult with execution results and artifacts
        """
        if input is None:
            return ToolExecutorResult()

        result = ToolExecutorResult()

        for action in input.actions:
            try:
                output = self.registry.execute(action, ctx.to_dict())

                if output is None:
                    result.actions_failed += 1
                    logger.warning(f"No tool available for action type: {action.type}")
                    continue

                if output.success:
                    result.actions_executed += 1

                    # Collect artifacts from tool output
                    if output.artifacts:
                        for artifact_data in output.artifacts:
                            result.artifacts_produced.append(
                                Artifact(
                                    type=artifact_data.get("type", ArtifactType.CUSTOM),
                                    payload=artifact_data.get("payload", {}),
                                    storage_uri=artifact_data.get("storage_uri"),
                                    mime_type=artifact_data.get("mime_type"),
                                    description=artifact_data.get("description"),
                                )
                            )

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

    async def run(self, ctx: PipelineContext, input: Any = None) -> StageResult:
        """Run the tool executor stage."""
        if not isinstance(input, Plan):
            return StageResult.ok()

        result = await self.execute(ctx, input)

        if result.error:
            return StageResult.error(result.error)

        # Add artifacts to context for downstream stages
        for artifact in result.artifacts_produced:
            ctx.artifacts.append(artifact)

        # Store execution metadata
        ctx.set_stage_metadata(
            self.id,
            {
                "actions_executed": result.actions_executed,
                "actions_failed": result.actions_failed,
                "artifacts_count": len(result.artifacts_produced),
                "requires_reentry": result.requires_reentry,
            },
        )

        return StageResult.ok()


__all__ = ["ToolExecutor", "ToolExecutorResult"]
