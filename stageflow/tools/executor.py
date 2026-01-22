"""Legacy ToolExecutor stage for executing agent actions.

Note: For new implementations, use AdvancedToolExecutor from executor_v2
which provides behavior gating, undo semantics, and HITL approval.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from .registry import get_tool_registry

if TYPE_CHECKING:
    from stageflow.helpers.memory_tracker import MemoryTracker
    from stageflow.helpers.uuid_utils import UuidCollisionMonitor
    from stageflow.pipeline.registry import PipelineRegistry
    from stageflow.pipeline.subpipeline import SubpipelineResult, SubpipelineSpawner
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
    subpipeline_runs: list[dict[str, Any]] = field(default_factory=list)


class ToolExecutor:
    """Pipeline stage that executes agent actions.

    The ToolExecutor:
    1. Receives a Plan from the agent
    2. For each action in the plan, looks up the corresponding tool
    3. Executes the action through the tool
    4. Collects any artifacts produced
    5. Determines if re-entry is needed (depends on action results)
    6. Can spawn subpipelines for complex multi-step operations

    Note: For advanced features like behavior gating, undo, and approval,
    use AdvancedToolExecutor instead.
    """

    id = "stage.tool_executor"

    def __init__(
        self,
        *,
        spawner: SubpipelineSpawner | None = None,
        registry: PipelineRegistry | None = None,
        uuid_monitor: UuidCollisionMonitor | None = None,
        memory_tracker: MemoryTracker | None = None,
    ) -> None:
        """Initialize ToolExecutor.

        Args:
            spawner: Optional SubpipelineSpawner for dependency injection (defaults to global).
            registry: Optional PipelineRegistry for dependency injection (defaults to global).
            uuid_monitor: Optional UUID collision monitor for telemetry.
            memory_tracker: Optional memory tracker for growth metrics.
        """
        self.tool_registry = get_tool_registry()
        self._spawner = spawner
        self._pipeline_registry = registry
        self._uuid_monitor = uuid_monitor
        self._memory_tracker = memory_tracker

    @property
    def spawner(self) -> SubpipelineSpawner:
        """Get the subpipeline spawner (lazy initialization)."""
        if self._spawner is None:
            from stageflow.pipeline.subpipeline import get_subpipeline_spawner

            self._spawner = get_subpipeline_spawner()
        return self._spawner

    @property
    def pipeline_registry(self) -> PipelineRegistry:
        """Get the pipeline registry (lazy initialization)."""
        if self._pipeline_registry is None:
            from stageflow.pipeline.registry import pipeline_registry

            self._pipeline_registry = pipeline_registry
        return self._pipeline_registry

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
                output = await self.tool_registry.execute(action, ctx.to_dict())

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

    async def spawn_subpipeline(
        self,
        pipeline_name: str,
        ctx: PipelineContext,
        correlation_id: UUID,
        *,
        topology_override: str | None = None,
        execution_mode_override: str | None = None,
    ) -> SubpipelineResult:
        """Spawn a child pipeline run.

        This method provides a high-level API for tools to spawn subpipelines.
        It handles:
        - Pipeline lookup from the registry
        - Building and executing the child pipeline graph
        - Full observability via SubpipelineSpawner events
        - Depth limit enforcement
        - Cancellation propagation

        Args:
            pipeline_name: Name of the registered pipeline to run.
            ctx: Parent PipelineContext (will be forked for the child).
            correlation_id: Action ID that triggered this spawn (for tracing).
            topology_override: Optional different topology for child pipeline.
            execution_mode_override: Optional different execution mode for child.

        Returns:
            SubpipelineResult with child run outcome (success, data, error, duration).

        Raises:
            MaxDepthExceededError: If spawning would exceed max nesting depth.
            KeyError: If pipeline_name is not found in registry.

        Example:
            ```python
            result = await executor.spawn_subpipeline(
                "validation_pipeline",
                ctx,
                action.id,
                execution_mode_override="strict",
            )
            if result.success:
                validated_data = result.data
            else:
                logger.error(f"Validation failed: {result.error}")
            ```
        """
        from stageflow.context import ContextSnapshot
        from stageflow.context.identity import RunIdentity
        from stageflow.core import PipelineTimer, StageContext
        from stageflow.pipeline.subpipeline import MaxDepthExceededError
        from stageflow.stages.inputs import create_stage_inputs

        start_time = time.perf_counter()
        parent_run_id = ctx.pipeline_run_id

        # Wire UUID monitor if present
        if self._uuid_monitor:
            self._uuid_monitor.observe(correlation_id)

        # Wire memory tracker if present
        if self._memory_tracker:
            self._memory_tracker.observe(label="subpipeline:start")

        logger.info(
            "Spawning subpipeline",
            extra={
                "pipeline_name": pipeline_name,
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "correlation_id": str(correlation_id),
                "parent_stage_id": self.id,
                "topology_override": topology_override,
                "execution_mode_override": execution_mode_override,
            },
        )

        # Resolve pipeline from registry (fail fast if not found)
        try:
            pipeline = self.pipeline_registry.get(pipeline_name)
        except KeyError:
            logger.error(
                f"Pipeline '{pipeline_name}' not found in registry",
                extra={
                    "pipeline_name": pipeline_name,
                    "parent_run_id": str(parent_run_id) if parent_run_id else None,
                    "correlation_id": str(correlation_id),
                },
            )
            raise

        # Build the pipeline graph once (avoid repeated builds)
        graph = pipeline.build()

        # Define the runner callable for SubpipelineSpawner
        async def runner(child_ctx: PipelineContext) -> dict[str, Any]:
            """Execute the child pipeline with the forked context.

            This runner creates a StageContext from the child PipelineContext
            and executes the pre-built graph. Returns stage outputs as dict.
            """
            # Create a minimal ContextSnapshot from child context for StageContext
            child_snapshot = ContextSnapshot(
                run_id=RunIdentity(
                    pipeline_run_id=child_ctx.pipeline_run_id,
                    request_id=child_ctx.request_id,
                    session_id=child_ctx.session_id,
                    user_id=child_ctx.user_id,
                    org_id=child_ctx.org_id,
                    interaction_id=child_ctx.interaction_id,
                ),
                topology=child_ctx.topology,
                execution_mode=child_ctx.execution_mode,
            )

            # Create stage inputs for the root
            root_inputs = create_stage_inputs(
                snapshot=child_snapshot,
                prior_outputs={},
                ports=None,
                declared_deps=(),
                stage_name="__subpipeline_root__",
            )

            # Create StageContext for graph execution
            stage_ctx = StageContext(
                snapshot=child_snapshot,
                inputs=root_inputs,
                stage_name="__subpipeline_root__",
                timer=PipelineTimer(),
                event_sink=child_ctx.event_sink,
            )

            # Execute the graph
            results = await graph.run(stage_ctx)

            # Convert StageOutput objects to dict
            return {name: output.data for name, output in results.items()}

        # Delegate to SubpipelineSpawner for full lifecycle management
        try:
            result = await self.spawner.spawn(
                pipeline_name=pipeline_name,
                ctx=ctx,
                correlation_id=correlation_id,
                parent_stage_id=self.id,
                runner=runner,
                topology=topology_override,
                execution_mode=execution_mode_override,
            )

            duration_ms = (time.perf_counter() - start_time) * 1000
            if self._memory_tracker:
                self._memory_tracker.observe(label="subpipeline:end")
            logger.info(
                "Subpipeline completed",
                extra={
                    "pipeline_name": pipeline_name,
                    "child_run_id": str(result.child_run_id),
                    "parent_run_id": str(parent_run_id) if parent_run_id else None,
                    "correlation_id": str(correlation_id),
                    "success": result.success,
                    "duration_ms": duration_ms,
                },
            )

            return result

        except MaxDepthExceededError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            if self._memory_tracker:
                self._memory_tracker.observe(label="subpipeline:depth_exceeded")
            logger.error(
                "Subpipeline spawn rejected: max depth exceeded",
                extra={
                    "pipeline_name": pipeline_name,
                    "parent_run_id": str(parent_run_id) if parent_run_id else None,
                    "correlation_id": str(correlation_id),
                    "duration_ms": duration_ms,
                },
            )
            raise

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            if self._memory_tracker:
                self._memory_tracker.observe(label="subpipeline:error")
            logger.error(
                f"Subpipeline spawn failed: {e}",
                extra={
                    "pipeline_name": pipeline_name,
                    "parent_run_id": str(parent_run_id) if parent_run_id else None,
                    "correlation_id": str(correlation_id),
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise


__all__ = ["ToolExecutor", "ToolExecutorResult"]
