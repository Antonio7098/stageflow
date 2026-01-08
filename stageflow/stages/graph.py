"""Unified StageGraph for the new Stage protocol.

This module provides a DAG executor that uses the unified Stage protocol:
- Stages implement Stage.execute(ctx: StageContext) -> StageOutput
- Uses StageContext instead of PipelineContext
- Uses StageOutput instead of StageResult

This is a parallel implementation to the original StageGraph in pipeline/dag.py.
Both can coexist during migration.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from stageflow.core.stages import (
    PipelineTimer,
    Stage,
    StageContext,
    StageKind,
    StageOutput,
    StageStatus,
)

from stageflow.stages.inputs import StageInputs, create_stage_inputs
from stageflow.stages.ports import create_stage_ports_from_data_dict

logger = logging.getLogger("unified_stage_graph")
DEBUG_LOG_PATH = "/tmp/debug_unified_pipeline.log"


def _debug_log(message: str) -> None:  # pragma: no cover - debug utility
    try:
        with open(DEBUG_LOG_PATH, "a") as f:
            f.write(f"[{datetime.now(UTC)}] [UnifiedStageGraph] {message}\n")
    except Exception:
        pass


@dataclass(slots=True, kw_only=True)
class UnifiedStageSpec:
    """Specification for a stage in the unified DAG."""

    name: str
    runner: Callable[[StageContext], Awaitable[StageOutput]]
    kind: StageKind
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    conditional: bool = False


class UnifiedStageExecutionError(Exception):
    """Raised when a stage inside a UnifiedStageGraph fails."""

    def __init__(self, stage: str, original: Exception, recoverable: bool = False) -> None:
        super().__init__(f"Stage '{stage}' failed: {original}")
        self.stage = stage
        self.original = original
        self.recoverable = recoverable


class UnifiedPipelineCancelled(Exception):
    """Raised when pipeline is cancelled by a stage.

    This is not an error - it's a graceful early termination.
    """

    def __init__(self, stage: str, reason: str, results: dict[str, StageOutput]) -> None:
        super().__init__(f"Pipeline cancelled by stage '{stage}': {reason}")
        self.stage = stage
        self.reason = reason
        self.results = results


class UnifiedStageGraph:
    """Dependency-driven DAG executor for unified Stage protocol.

    Executes stages as soon as their dependencies are met, allowing
    for maximum parallelism. Uses StageContext and StageOutput.

    Features:
    - Dependency-driven execution (topological sort)
    - Parallel execution where possible
    - Conditional stage support
    - Cancellation support
    - Structured logging with stage events
    """

    def __init__(
        self,
        specs: Iterable[UnifiedStageSpec],
    ) -> None:
        self._specs = {spec.name: spec for spec in specs}
        if len(self._specs) == 0:
            raise ValueError("UnifiedStageGraph requires at least one UnifiedStageSpec")

    @property
    def stage_specs(self) -> list[UnifiedStageSpec]:
        """Get list of stage specs."""
        return list(self._specs.values())

    def _duration_ms(self, started_at: datetime, ended_at: datetime) -> int:
        return int((ended_at - started_at).total_seconds() * 1000)

    async def run(self, ctx: StageContext) -> dict[str, StageOutput]:
        """Execute the DAG with the given context.

        Args:
            ctx: StageContext containing the snapshot and config

        Returns:
            Dict mapping stage name to StageOutput
        """
        _debug_log(f"run starting with stages: {list(self._specs.keys())}")

        logger.info(
            "UnifiedStageGraph execution started",
            extra={
                "event": "graph_started",
                "stage_count": len(self._specs),
                "stages": list(self._specs.keys()),
            },
        )

        # Create a shared pipeline timer for consistent cross-stage timing
        shared_timer = ctx.config.get("timer") or PipelineTimer()

        completed: dict[str, StageOutput] = {}
        in_degree: dict[str, int] = {
            name: len(set(spec.dependencies)) for name, spec in self._specs.items()
        }
        active_tasks: set[asyncio.Task[tuple[str, StageOutput]]] = set()

        def schedule_stage(name: str) -> None:
            task = asyncio.create_task(self._execute_node(name, ctx, completed, shared_timer))
            active_tasks.add(task)
            _debug_log(f"Stage {name} scheduled")

        # Seed the graph with stages that have no dependencies
        ready_nodes = [name for name, count in in_degree.items() if count == 0]
        for name in ready_nodes:
            schedule_stage(name)

        # Main execution loop
        while len(completed) < len(self._specs):
            if not active_tasks:
                pending = sorted(set(self._specs) - set(completed))
                error_msg = f"Deadlocked stage graph; remaining stages: {pending}"
                logger.error(
                    "Deadlock detected in stage graph",
                    extra={
                        "event": "deadlock",
                        "pending_stages": pending,
                    },
                )
                raise RuntimeError(error_msg)

            # Wait for at least one task to finish
            done, _ = await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)

            for task in done:
                active_tasks.remove(task)

                # Check for exceptions
                if task.exception():
                    # Cancel all other active tasks before raising
                    for t in active_tasks:
                        t.cancel()
                    if active_tasks:
                        await asyncio.gather(*active_tasks, return_exceptions=True)

                    exc = task.exception()
                    logger.error(
                        f"Stage task execution failed: {exc}",
                        extra={
                            "event": "stage_failed",
                            "error": str(exc),
                        },
                        exc_info=True,
                    )
                    raise exc  # type: ignore[misc]

                # Success - get result
                stage_name, stage_output = task.result()
                completed[stage_name] = stage_output

                # Handle CANCEL status - stop pipeline gracefully
                if stage_output.status == StageStatus.CANCEL:
                    logger.info(
                        f"Pipeline cancelled by stage {stage_name}: {stage_output.data.get('cancel_reason', 'no reason')}",
                        extra={
                            "event": "pipeline_cancelled",
                            "stage": stage_name,
                            "reason": stage_output.data.get("cancel_reason", ""),
                            "stages_completed": list(completed.keys()),
                        },
                    )
                    # Cancel all other active tasks
                    for t in active_tasks:
                        t.cancel()
                    if active_tasks:
                        await asyncio.gather(*active_tasks, return_exceptions=True)
                    # Return completed results (partial)
                    raise UnifiedPipelineCancelled(
                        stage=stage_name,
                        reason=stage_output.data.get("cancel_reason", "Pipeline cancelled"),
                        results=completed,
                    )

                logger.info(
                    f"Stage {stage_name} completed with status={stage_output.status.value}, data_keys={list(stage_output.data.keys())}",
                    extra={
                        "event": "stage_completed",
                        "stage": stage_name,
                        "status": stage_output.status.value,
                        "data_keys": list(stage_output.data.keys()),
                    },
                )

                # Unlock dependencies
                for potential_child, spec in self._specs.items():
                    if stage_name in spec.dependencies:
                        in_degree[potential_child] -= 1
                        if in_degree[potential_child] == 0:
                            schedule_stage(potential_child)

        logger.info(
            "UnifiedStageGraph execution completed",
            extra={
                "event": "graph_completed",
                "stages_completed": list(completed.keys()),
                "stage_count": len(completed),
            },
        )

        return completed

    async def _execute_node(
        self,
        name: str,
        ctx: StageContext,
        completed: dict[str, StageOutput],
        shared_timer: PipelineTimer,
    ) -> tuple[str, StageOutput]:
        """Execute a single stage and return its output.

        Creates a fresh StageContext with StageInputs containing only
        outputs from declared dependencies, ensuring immutability.
        """
        spec = self._specs[name]

        prior_outputs = {
            dep_name: output
            for dep_name, output in completed.items()
            if dep_name in spec.dependencies
        }

        # Preserve the original ports from the initial context
        original_inputs: StageInputs | None = ctx.config.get("inputs")
        if original_inputs is not None:
            ports = original_inputs.ports
        else:
            ports = create_stage_ports_from_data_dict(ctx.config.get("data", {}))

        # Debug log for TTS stage
        if name == "tts_incremental":
            send_audio_chunk = getattr(ports, "send_audio_chunk", None)
            logger.info(
                f"tts_incremental stage execution: send_audio_chunk={'set' if send_audio_chunk else 'None'}, "
                f"ports.send_audio_chunk={ports.send_audio_chunk}"
            )

        inputs = create_stage_inputs(
            snapshot=ctx.snapshot,
            prior_outputs=prior_outputs,
            ports=ports,
        )

        # Pass the shared timer for consistent cross-stage timing
        stage_ctx = StageContext(
            snapshot=ctx.snapshot,
            config={"inputs": inputs, "timer": shared_timer},
        )

        return name, await self._run_stage(spec, stage_ctx)

    async def _run_stage(self, spec: UnifiedStageSpec, ctx: StageContext) -> StageOutput:
        """Run a stage with normalization and structured logging."""
        started_at = datetime.now(UTC)

        logger.info(
            f"Running stage: {spec.name}",
            extra={
                "event": "stage_started",
                "stage": spec.name,
                "kind": spec.kind.value,
            },
        )

        # Handle conditional stages
        if spec.conditional:
            # Check both ctx._outputs (emitted outputs) and inputs.prior_outputs (dependency outputs)
            skip_reason = ctx.get_output_data("skip_reason")
            if skip_reason is None:
                # Also check prior_outputs from dependencies
                inputs = ctx.config.get("inputs")
                if inputs is not None:
                    skip_reason = inputs.get("skip_reason")
            if skip_reason:
                logger.info(
                    f"Skipping conditional stage: {spec.name}",
                    extra={
                        "event": "stage_skipped",
                        "stage": spec.name,
                        "reason": skip_reason,
                    },
                )
                ctx.emit_event("stage_skipped", {"stage": spec.name, "reason": skip_reason})
                return StageOutput.skip(reason=skip_reason)

        try:
            # Execute the stage
            raw_output = await spec.runner(ctx)
            ended_at = datetime.now(UTC)

            # Normalize output
            result = self._normalize_output(spec.name, raw_output, started_at)

            duration_ms = self._duration_ms(started_at, ended_at)

            logger.info(
                f"Stage {spec.name} completed with status={result.status.value}",
                extra={
                    "event": "stage_completed",
                    "stage": spec.name,
                    "status": result.status.value,
                    "duration_ms": duration_ms,
                },
            )

            # Emit completion event
            ctx.emit_event(
                "stage_completed",
                {
                    "stage": spec.name,
                    "status": result.status.value,
                    "duration_ms": duration_ms,
                },
            )

            # Check if stage returned failed status
            if result.status == StageStatus.FAIL:
                logger.error(
                    f"Stage {spec.name} failed: {result.error}",
                    extra={
                        "event": "stage_failed",
                        "stage": spec.name,
                        "error": result.error,
                        "duration_ms": duration_ms,
                    },
                )
                raise UnifiedStageExecutionError(
                    stage=spec.name,
                    original=Exception(result.error or "Stage failed"),
                )

            return result

        except UnifiedStageExecutionError:
            raise
        except Exception as exc:
            logger.exception(
                f"Stage {spec.name} failed with error: {exc}",
                extra={
                    "event": "stage_error",
                    "stage": spec.name,
                    "error": str(exc),
                },
            )
            raise UnifiedStageExecutionError(spec.name, exc) from exc

    @staticmethod
    def _normalize_output(
        name: str,
        raw: StageOutput | dict | None,
        _started_at: datetime,
    ) -> StageOutput:
        """Normalize stage output to StageOutput."""
        if raw is None:
            return StageOutput.ok()

        if isinstance(raw, StageOutput):
            return raw

        if isinstance(raw, dict):
            return StageOutput.ok(data=raw)

        raise TypeError(f"Stage {name} returned unsupported result type {type(raw)}")


class StageRunnerAdapter:
    """Adapter that wraps a legacy StageRunner to work with UnifiedStageGraph.

    Converts the old signature:
        runner(ctx: PipelineContext) -> Awaitable[StageResult | dict | None]

    To the new signature:
        runner(ctx: StageContext) -> Awaitable[StageOutput]
    """

    def __init__(
        self,
        *,
        runner: Callable[[StageContext], Awaitable[StageOutput]],
        name: str,
        kind: StageKind,
        dependencies: tuple[str, ...] | None = None,
    ) -> None:
        self._runner = runner
        self.name = name
        self.kind = kind
        self.dependencies = dependencies or ()

    async def __call__(self, ctx: StageContext) -> StageOutput:
        """Execute the adapted runner."""
        return await self._runner(ctx)


def create_unified_spec_from_stage(
    stage: Stage,
    *,
    runner: Callable[[StageContext], Awaitable[StageOutput]] | None = None,
    dependencies: tuple[str, ...] | None = None,
) -> UnifiedStageSpec:
    """Create a UnifiedStageSpec from a Stage instance.

    Args:
        stage: The Stage instance
        runner: Optional runner override (defaults to stage.execute)
        dependencies: Optional dependencies override

    Returns:
        UnifiedStageSpec ready for UnifiedStageGraph
    """
    actual_runner = runner or stage.execute
    return UnifiedStageSpec(
        name=stage.name,
        runner=actual_runner,
        kind=stage.kind,
        dependencies=dependencies or (),
    )


__all__ = [
    "UnifiedStageSpec",
    "UnifiedStageExecutionError",
    "UnifiedPipelineCancelled",
    "UnifiedStageGraph",
    "StageRunnerAdapter",
    "create_unified_spec_from_stage",
]
