from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from stageflow.core.stages import StageOutput, StageStatus
from stageflow.pipeline.interceptors import (
    BaseInterceptor,
    get_default_interceptors,
    run_with_interceptors,
)
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageError, StageResult

DEBUG_LOG_PATH = "/tmp/debug_pipeline_dag.log"

StageRunner = Callable[[PipelineContext], Awaitable[StageResult | dict | None]]


@dataclass(slots=True, kw_only=True)
class StageSpec:
    name: str
    runner: StageRunner
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    conditional: bool = False


class StageExecutionError(StageError):
    """Raised when a stage inside a StageGraph fails."""

    def __init__(self, stage: str, original: Exception, recoverable: bool = False) -> None:
        super().__init__(stage=stage, original=original)
        self.recoverable = recoverable


class StageGraph:
    """Minimal dependency-driven stage-DAG executor.

    Executes stages as soon as their dependencies are met, allowing for maximum parallelism.
    Supports conditional stages that can be skipped based on triage results.
    Supports cancellation via PipelineContext.canceled flag.
    Supports interceptor middleware via stage execution wrapping.
    """

    def __init__(
        self,
        specs: Iterable[StageSpec],
        interceptors: list[BaseInterceptor] | None = None,
    ) -> None:
        self._specs = {spec.name: spec for spec in specs}
        if len(self._specs) == 0:
            raise ValueError("StageGraph requires at least one StageSpec")
        self._interceptors = interceptors or get_default_interceptors()

    @property
    def stage_specs(self) -> list[StageSpec]:
        """Get list of stage specs for compatibility with voice service."""
        return list(self._specs.values())

    def _duration_ms(self, started_at: datetime, ended_at: datetime) -> int:
        return int((ended_at - started_at).total_seconds() * 1000)

    @staticmethod
    def _debug_log(message: str) -> None:  # pragma: no cover - debug utility
        try:
            with open(DEBUG_LOG_PATH, "a") as f:
                f.write(f"{message}\n")
        except Exception:
            pass

    async def run(self, ctx: PipelineContext) -> dict[str, StageResult]:
        try:
            with open("/tmp/debug_voice_handler.log", "a") as f:
                f.write(
                    f"\n[{datetime.now(UTC)}] StageGraph.run starting with specs: {list(self._specs.keys())}\n"
                )
        except Exception as exc:  # pragma: no cover - defensive logging path
            import logging

            logger = logging.getLogger("pipeline_dag")
            logger.error(f"Failed to write debug log: {exc}", exc_info=True)

        completed: dict[str, StageResult] = {}
        # Track how many dependencies each stage is still waiting for (deduplicated)
        in_degree = {name: len(set(spec.dependencies)) for name, spec in self._specs.items()}

        # Active tasks
        active_tasks: set[asyncio.Task[tuple[str, StageResult]]] = set()

        # Helper to launch a stage
        def schedule_stage(name: str) -> None:
            task = asyncio.create_task(self._execute_node(name, ctx))
            active_tasks.add(task)

            try:
                with open("/tmp/debug_voice_handler.log", "a") as f:
                    f.write(f"  Stage {name} scheduled/started.\n")
            except Exception as exc:  # pragma: no cover - defensive logging path
                import logging

                logger = logging.getLogger("pipeline_dag")
                logger.error(f"Failed to write debug log: {exc}", exc_info=True)

        # Seed the graph with stages that have no dependencies
        ready_nodes = [name for name, count in in_degree.items() if count == 0]
        for name in ready_nodes:
            schedule_stage(name)

        # Main loop: wait for tasks to complete and schedule dependents
        while len(completed) < len(self._specs):
            if not active_tasks:
                pending = sorted(set(self._specs) - set(completed))
                raise RuntimeError(f"Deadlocked stage graph; remaining stages: {pending}")

            # Check for cancellation
            if ctx.canceled:
                # Cancel all active tasks
                for task in active_tasks:
                    task.cancel()
                if active_tasks:
                    await asyncio.gather(*active_tasks, return_exceptions=True)
                # Mark remaining stages as canceled
                for name in set(self._specs) - set(completed):
                    completed[name] = StageResult(
                        name=name,
                        status="failed",
                        started_at=datetime.now(UTC),
                        ended_at=datetime.now(UTC),
                        error="Pipeline canceled",
                    )
                break

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
                    raise task.exception()  # type: ignore[misc]

                # Success
                stage_name, stage_result = task.result()
                completed[stage_name] = stage_result

                # Unlock dependencies
                for potential_child, spec in self._specs.items():
                    if stage_name in spec.dependencies:
                        in_degree[potential_child] -= 1
                        if in_degree[potential_child] == 0:
                            schedule_stage(potential_child)

        return completed

    async def _execute_node(self, name: str, ctx: PipelineContext) -> tuple[str, StageResult]:
        """Internal wrapper to run the stage and store result."""
        spec = self._specs[name]
        result = await self._run_stage(spec, ctx)
        return name, result

    async def _run_stage(self, spec: StageSpec, ctx: PipelineContext) -> StageResult:
        started_at = datetime.now(UTC)
        import logging

        logger = logging.getLogger("pipeline_dag")

        # Check if this is a conditional stage that should be skipped
        if spec.conditional:
            skip_assessment = ctx.data.get("skip_assessment", False)
            if skip_assessment:
                logger.info(f"[DEBUG] Skipping conditional stage: {spec.name}")
                # Emit status events for skipped conditional stages (for test compatibility)
                send_status = ctx.data.get("send_status")
                if send_status and callable(send_status):
                    await send_status(spec.name, "started", {"skipped": True})
                    await send_status(
                        spec.name,
                        "completed",
                        {"skipped": True, "reason": "triage_decision"},
                    )
                ctx.record_stage_event(
                    stage=spec.name,
                    status="skipped",  # type: ignore[arg-type]
                    payload={"reason": "triage_decision"},
                )
                ended_at = datetime.now(UTC)
                return StageResult(
                    name=spec.name,
                    status="completed",
                    started_at=started_at,
                    ended_at=ended_at,
                    data={"skipped": True, "reason": "triage_decision"},
                )

        logger.info(f"[DEBUG] Running stage: {spec.name}")
        ctx.record_stage_event(stage=spec.name, status="started")

        # Wrap stage execution with interceptors
        async def run_stage() -> StageResult:
            """Inner function to run the stage runner."""
            # Instantiate the stage and call execute
            stage_instance = spec.runner()  # type: ignore[operator]
            raw_result = await stage_instance.execute(ctx)  # type: ignore[attr-defined]

            ended_at = datetime.now(UTC)
            return self._normalize_result(spec.name, raw_result, started_at, ended_at)  # type: ignore[arg-type]

        try:
            # Execute with interceptor wrapping
            result = await run_with_interceptors(
                stage_name=spec.name,
                stage_run=run_stage,
                ctx=ctx,
                interceptors=self._interceptors,
            )

            self._debug_log(
                f"[{datetime.now(UTC)}] Stage {spec.name} completed with status={result.status}"
            )

            # Check if the stage returned a failed status (stage handled error internally)
            if result.status == "failed":
                ctx.record_stage_event(
                    stage=spec.name,
                    status="failed",
                    payload={
                        "duration_ms": self._duration_ms(started_at, result.ended_at),
                        "error": result.error or "Stage returned failed status",
                    },
                )
            else:
                ctx.record_stage_event(
                    stage=spec.name,
                    status="completed",
                    payload={"duration_ms": self._duration_ms(started_at, result.ended_at)},
                )
            return result
        except Exception as exc:  # pragma: no cover - defensive
            self._debug_log(f"[{datetime.now(UTC)}] Stage {spec.name} failed with error={exc!r}")
            ctx.record_stage_event(
                stage=spec.name,
                status="failed",
                payload={
                    "duration_ms": self._duration_ms(started_at, datetime.now(UTC)),
                    "error": str(exc),
                },
            )
            raise StageExecutionError(spec.name, exc) from exc

    @staticmethod
    def _normalize_result(
        name: str,
        raw: StageResult | StageOutput | dict | None,
        started_at: datetime,
        ended_at: datetime,
    ) -> StageResult:
        if isinstance(raw, StageResult):
            return raw

        if isinstance(raw, StageOutput):
            # Convert StageOutput status to StageResult status
            if raw.status == StageStatus.OK:
                status = "completed"
            elif raw.status == StageStatus.FAIL:
                status = "failed"
            elif raw.status == StageStatus.SKIP:
                status = "completed"  # Skipped stages are still "completed"
            elif raw.status == StageStatus.CANCEL:
                status = "completed"  # Cancelled stages are "completed" for graph purposes
            else:
                status = "completed"  # Default to completed for unknown statuses

            return StageResult(
                name=name,
                status=status,  # type: ignore
                started_at=started_at,
                ended_at=ended_at,
                data=raw.data,
                error=raw.error,
            )

        data = raw or {}
        if not isinstance(data, dict):
            raise TypeError(f"Stage {name} returned unsupported result type {type(raw)}")

        return StageResult(
            name=name,
            status="completed",
            started_at=started_at,
            ended_at=ended_at,
            data=data,
        )


__all__ = ["StageExecutionError", "StageGraph", "StageSpec"]
