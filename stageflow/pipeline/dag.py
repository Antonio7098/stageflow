from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from warnings import warn

from stageflow.core import (
    PipelineTimer,
    StageCancellationRequested,
    StageContext,
    StageKind,
    StageOutput,
    StageReturn,
    StageStatus,
)
from stageflow.observability.wide_events import WideEventEmitter
from stageflow.pipeline.cancellation import (
    CancellationToken,
    CleanupRegistry,
)
from stageflow.pipeline.guard_retry import (
    GuardRetryPolicy,
    GuardRetryStrategy,
    hash_retry_payload,
)
from stageflow.pipeline.interceptors import (
    BaseInterceptor,
    get_default_interceptors,
    run_with_interceptors,
)
from stageflow.pipeline.results import PipelineResults
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageError, StageResult

logger = logging.getLogger("pipeline_dag")
DEBUG_LOG_PATH = "/tmp/debug_pipeline_dag.log"

StageRunner = Callable[[PipelineContext], Awaitable[StageResult | dict | None]]
StageRunnerNew = Callable[[StageContext], Awaitable[StageReturn]]


@dataclass(slots=True, kw_only=True)
class StageSpec:
    name: str
    runner: StageRunner
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    conditional: bool = False


@dataclass(slots=True, kw_only=True)
class UnifiedStageSpec:
    """Specification for a stage in the unified DAG."""

    name: str
    runner: StageRunnerNew
    kind: StageKind | None = None
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    conditional: bool = False


@dataclass(slots=True)
class GuardRetryRuntimeState:
    attempts: int = 0
    stagnation_hits: int = 0
    last_hash: str | None = None
    started_at: float | None = None


class StageExecutionError(StageError):
    """Raised when a stage inside a StageGraph fails."""

    def __init__(self, stage: str, original: Exception, recoverable: bool = False) -> None:
        super().__init__(stage=stage, original=original)
        self.recoverable = recoverable


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
        self.results = PipelineResults(results)


class StageGraph:
    """Dependency-driven stage-DAG executor.

    Executes stages as soon as their dependencies are met, allowing for maximum parallelism.
    Supports conditional stages.
    Supports cancellation via PipelineContext.canceled flag.
    Supports interceptor middleware via stage execution wrapping.
    """

    def __init__(
        self,
        specs: Iterable[StageSpec],
        interceptors: list[BaseInterceptor] | None = None,
        *,
        wide_event_emitter: WideEventEmitter | None = None,
        emit_stage_wide_events: bool = False,
        emit_pipeline_wide_event: bool = False,
    ) -> None:
        warn(
            "StageGraph is deprecated; use Pipeline.build() / UnifiedStageGraph for new code.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._specs = {spec.name: spec for spec in specs}
        if len(self._specs) == 0:
            raise ValueError("StageGraph requires at least one StageSpec")
        self._interceptors = interceptors or get_default_interceptors()
        if wide_event_emitter is None and (emit_stage_wide_events or emit_pipeline_wide_event):
            wide_event_emitter = WideEventEmitter()
        self._wide_event_emitter = wide_event_emitter
        self._emit_stage_wide_events = emit_stage_wide_events and wide_event_emitter is not None
        self._emit_pipeline_wide_event = emit_pipeline_wide_event and wide_event_emitter is not None

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
        graph_started_at = datetime.now(UTC)
        try:
            with open("/tmp/debug_voice_handler.log", "a") as f:
                f.write(
                    f"\n[{datetime.now(UTC)}] StageGraph.run starting with specs: {list(self._specs.keys())}\n"
                )
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.error(f"Failed to write debug log: {exc}", exc_info=True)

        completed: dict[str, StageResult] = {}
        in_degree = {name: len(set(spec.dependencies)) for name, spec in self._specs.items()}
        active_tasks: set[asyncio.Task[tuple[str, StageResult]]] = set()

        def schedule_stage(name: str) -> None:
            task = asyncio.create_task(self._execute_node(name, ctx))
            active_tasks.add(task)

            try:
                with open("/tmp/debug_voice_handler.log", "a") as f:
                    f.write(f"  Stage {name} scheduled/started.\n")
            except Exception as exc:  # pragma: no cover - defensive logging path
                logger.error(f"Failed to write debug log: {exc}", exc_info=True)

        ready_nodes = [name for name, count in in_degree.items() if count == 0]
        for name in ready_nodes:
            schedule_stage(name)

        while len(completed) < len(self._specs):
            if not active_tasks:
                pending = sorted(set(self._specs) - set(completed))
                raise RuntimeError(f"Deadlocked stage graph; remaining stages: {pending}")

            if ctx.canceled:
                for task in active_tasks:
                    task.cancel()
                if active_tasks:
                    await asyncio.gather(*active_tasks, return_exceptions=True)
                for name in set(self._specs) - set(completed):
                    completed[name] = StageResult(
                        name=name,
                        status="failed",
                        started_at=datetime.now(UTC),
                        ended_at=datetime.now(UTC),
                        error="Pipeline canceled",
                    )
                break

            done, _ = await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)

            for task in done:
                active_tasks.remove(task)

                if task.exception():
                    for t in active_tasks:
                        t.cancel()
                    if active_tasks:
                        await asyncio.gather(*active_tasks, return_exceptions=True)
                    raise task.exception()  # type: ignore[misc]

                stage_name, stage_result = task.result()
                completed[stage_name] = stage_result

                for potential_child, spec in self._specs.items():
                    if stage_name in spec.dependencies:
                        in_degree[potential_child] -= 1
                        if in_degree[potential_child] == 0:
                            schedule_stage(potential_child)

        if self._emit_pipeline_wide_event and self._wide_event_emitter is not None:
            duration_ms = int((datetime.now(UTC) - graph_started_at).total_seconds() * 1000)
            self._wide_event_emitter.emit_pipeline_event(
                ctx=ctx,
                stage_results=completed,
                pipeline_name=ctx.topology,
                status=None,
                duration_ms=duration_ms,
                started_at=graph_started_at,
            )

        return completed

    async def _execute_node(self, name: str, ctx: PipelineContext) -> tuple[str, StageResult]:
        spec = self._specs[name]
        result = await self._run_stage(spec, ctx)
        return name, result

    async def _run_stage(self, spec: StageSpec, ctx: PipelineContext) -> StageResult:
        started_at = datetime.now(UTC)

        logger.info(f"[DEBUG] Running stage: {spec.name}")
        ctx.record_stage_event(stage=spec.name, status="started")

        async def run_stage() -> StageResult:
            # Handle both cases:
            # 1. Runner is a class - instantiate and call execute()
            # 2. Runner is an async function (from PipelineBuilder.build) - call directly
            runner = spec.runner
            if isinstance(runner, type):
                # It's a class, instantiate it
                stage_instance = runner()
                raw_result = await stage_instance.execute(ctx)
            else:
                # It's an async function that takes ctx
                raw_result = await runner(ctx)  # type: ignore[operator]
            ended_at = datetime.now(UTC)
            return self._normalize_result(spec.name, raw_result, started_at, ended_at)  # type: ignore[arg-type]

        try:
            result = await run_with_interceptors(
                stage_name=spec.name,
                stage_run=run_stage,
                ctx=ctx,
                interceptors=self._interceptors,
            )

            self._debug_log(
                f"[{datetime.now(UTC)}] Stage {spec.name} completed with status={result.status}"
            )

            duration_ms = self._duration_ms(started_at, result.ended_at)
            if result.status == "failed":
                ctx.record_stage_event(
                    stage=spec.name,
                    status="failed",
                    payload={
                        "duration_ms": duration_ms,
                        "error": result.error or "Stage returned failed status",
                    },
                )
            else:
                ctx.record_stage_event(
                    stage=spec.name,
                    status="completed",
                    payload={"duration_ms": duration_ms},
                )

            if self._emit_stage_wide_events and self._wide_event_emitter is not None:
                self._wide_event_emitter.emit_stage_event(ctx=ctx, result=result)
            return result
        except Exception as exc:  # pragma: no cover - defensive
            ended_at = datetime.now(UTC)
            self._debug_log(f"[{ended_at}] Stage {spec.name} failed with error={exc!r}")
            ctx.record_stage_event(
                stage=spec.name,
                status="failed",
                payload={
                    "duration_ms": self._duration_ms(started_at, ended_at),
                    "error": str(exc),
                },
            )
            if self._emit_stage_wide_events and self._wide_event_emitter is not None:
                failure_result = StageResult(
                    name=spec.name,
                    status="failed",
                    started_at=started_at,
                    ended_at=ended_at,
                    error=str(exc),
                )
                self._wide_event_emitter.emit_stage_event(ctx=ctx, result=failure_result)
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
            if raw.status == StageStatus.OK:
                status = "completed"
            elif raw.status == StageStatus.FAIL:
                status = "failed"
            elif raw.status == StageStatus.SKIP or raw.status == StageStatus.CANCEL:
                status = "completed"
            else:
                status = "completed"

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


class UnifiedStageGraph:
    """Dependency-driven DAG executor for unified Stage protocol.

    Executes stages as soon as their dependencies are met, allowing
    for maximum parallelism. Uses StageContext and StageOutput.

    Features:
    - Dependency-driven execution (topological sort)
    - Parallel execution where possible
    - Conditional stage support
    - Interceptor middleware support (same contract as StageGraph)
    - Cancellation support with structured cleanup
    - Structured logging with stage events
    """

    def __init__(
        self,
        specs: Iterable[UnifiedStageSpec],
        *,
        pipeline_name: str | None = None,
        interceptors: list[BaseInterceptor] | None = None,
        cleanup_timeout: float = 10.0,
        guard_retry_strategy: GuardRetryStrategy | None = None,
        wide_event_emitter: WideEventEmitter | None = None,
        emit_stage_wide_events: bool = False,
        emit_pipeline_wide_event: bool = False,
    ) -> None:
        self._specs = {spec.name: spec for spec in specs}
        if len(self._specs) == 0:
            raise ValueError("UnifiedStageGraph requires at least one UnifiedStageSpec")
        self._interceptors = interceptors or get_default_interceptors()
        self._cleanup_timeout = cleanup_timeout
        self._cleanup_registry: CleanupRegistry | None = None
        self._cancel_token: CancellationToken | None = None
        self._guard_retry_strategy = guard_retry_strategy
        self._pipeline_name = pipeline_name
        if wide_event_emitter is None and (emit_stage_wide_events or emit_pipeline_wide_event):
            wide_event_emitter = WideEventEmitter()
        self._wide_event_emitter = wide_event_emitter
        self._emit_stage_wide_events = emit_stage_wide_events and wide_event_emitter is not None
        self._emit_pipeline_wide_event = emit_pipeline_wide_event and wide_event_emitter is not None
        if self._guard_retry_strategy is not None:
            self._guard_retry_strategy.validate(self._specs)

    @property
    def cleanup_registry(self) -> CleanupRegistry | None:
        """Get the cleanup registry for the current execution."""
        return self._cleanup_registry

    @property
    def cancel_token(self) -> CancellationToken | None:
        """Get the cancellation token for the current execution."""
        return self._cancel_token

    def register_cleanup(self, callback, *, name: str | None = None) -> None:
        """Register a cleanup callback for the current execution.

        Args:
            callback: Async function to call during cleanup.
            name: Optional name for logging/debugging.
        """
        if self._cleanup_registry is not None:
            self._cleanup_registry.register(callback, name=name)

    @property
    def stage_specs(self) -> list[UnifiedStageSpec]:
        """Get list of stage specs."""
        return list(self._specs.values())

    def _duration_ms(self, started_at: datetime, ended_at: datetime) -> int:
        return int((ended_at - started_at).total_seconds() * 1000)

    def _publish_stage_wide_event(self, ctx: PipelineContext, result: StageResult) -> None:
        if not self._emit_stage_wide_events or self._wide_event_emitter is None:
            return
        self._wide_event_emitter.emit_stage_event(ctx=ctx, result=result)

    def _publish_pipeline_wide_event(
        self,
        ctx: PipelineContext,
        stage_results: dict[str, StageResult],
        *,
        started_at: datetime,
        status: str,
    ) -> None:
        if not self._emit_pipeline_wide_event or self._wide_event_emitter is None:
            return
        self._wide_event_emitter.emit_pipeline_event(
            ctx=ctx,
            stage_results=stage_results,
            pipeline_name=self._pipeline_name or ctx.topology,
            status=status,
            duration_ms=self._duration_ms(started_at, datetime.now(UTC)),
            started_at=started_at,
        )

    async def run(self, ctx: StageContext | PipelineContext) -> PipelineResults:
        """Execute the DAG with the given context.

        Uses structured cancellation to ensure proper resource cleanup
        when the pipeline is cancelled or encounters an error.

        Args:
            ctx: Root context for execution. Preferred entry is PipelineContext;
                StageContext remains supported for backwards compatibility.

        Returns:
            PipelineResults mapping stage name to StageOutput
        """
        graph_started_at = datetime.now(UTC)
        logger.info(
            "UnifiedStageGraph execution started",
            extra={
                "event": "graph_started",
                "stage_count": len(self._specs),
                "stages": list(self._specs.keys()),
            },
        )

        if isinstance(ctx, PipelineContext):
            stage_ctx = ctx.derive_root_stage_context()
            interceptor_ctx = ctx
        else:
            warn(
                "UnifiedStageGraph.run(StageContext) is deprecated; pass PipelineContext at orchestration boundaries.",
                DeprecationWarning,
                stacklevel=2,
            )
            stage_ctx = ctx
            # StageContext-only entrypoints use a derived mutable context for interceptors.
            interceptor_ctx = ctx.as_pipeline_context()

        # Initialize cleanup registry and cancellation token for this execution
        self._cleanup_registry = CleanupRegistry()
        self._cancel_token = CancellationToken()

        shared_timer = stage_ctx.timer or PipelineTimer()

        completed: dict[str, StageOutput] = {}
        completed_results: dict[str, StageResult] = {}
        guard_retry_state: dict[str, GuardRetryRuntimeState] = {}
        pending_guard_retries: dict[str, list[str]] = defaultdict(list)
        finalized: set[str] = set()
        active_retry_targets: set[str] = set()
        in_degree: dict[str, int] = {
            name: len(set(spec.dependencies)) for name, spec in self._specs.items()
        }
        active_tasks: set[asyncio.Task[tuple[str, StageOutput, StageResult]]] = set()

        def emit_guard_retry_event(event: str, **payload: Any) -> None:
            try:
                stage_ctx.try_emit_event(type=f"guard_retry.{event}", data=payload)
            except AttributeError:
                logger.debug(
                    "Guard retry event skipped (no context emitter)",
                    extra={"event": "guard_retry_event_skipped", "payload": payload},
                )

        async def run_cleanup() -> None:
            """Run all registered cleanup callbacks."""
            if self._cleanup_registry and self._cleanup_registry.pending_count > 0:
                logger.info(
                    f"Running {self._cleanup_registry.pending_count} cleanup callbacks",
                    extra={"event": "cleanup_started"},
                )
                completed_cleanups, failed_cleanups = await self._cleanup_registry.run_all(
                    timeout=self._cleanup_timeout
                )
                logger.info(
                    "Cleanup completed",
                    extra={
                        "event": "cleanup_completed",
                        "completed": completed_cleanups,
                        "failed": [name for name, _ in failed_cleanups],
                    },
                )

        def schedule_stage(name: str) -> None:
            task = asyncio.create_task(
                self._execute_node(
                    name,
                    stage_ctx,
                    completed,
                    shared_timer,
                    interceptor_ctx,
                )
            )
            active_tasks.add(task)

        try:
            ready_nodes = [name for name, count in in_degree.items() if count == 0]
            for name in ready_nodes:
                schedule_stage(name)

            while len(finalized) < len(self._specs):
                # Check for cooperative cancellation
                if interceptor_ctx.is_canceled or (
                    self._cancel_token and self._cancel_token.is_cancelled
                ):
                    reason = (
                        interceptor_ctx.cancellation_reason
                        or (self._cancel_token.reason if self._cancel_token else None)
                        or "Cancelled"
                    )
                    logger.info(
                        f"Pipeline cancelled via token: {reason}",
                        extra={
                            "event": "pipeline_cancelled_token",
                            "reason": reason,
                        },
                    )
                    for t in active_tasks:
                        t.cancel()
                    if active_tasks:
                        await asyncio.gather(*active_tasks, return_exceptions=True)
                    raise UnifiedPipelineCancelled(
                        stage="<external>",
                        reason=reason,
                        results=PipelineResults(completed),
                    )

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

                done, _ = await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)

                for task in done:
                    active_tasks.remove(task)

                    if task.exception():
                        # Cancel remaining tasks
                        if self._cancel_token:
                            self._cancel_token.cancel("Stage failed")
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

                    stage_name, stage_output, stage_result = task.result()

                    policy: GuardRetryPolicy | None = None
                    spec = self._specs[stage_name]
                    if self._guard_retry_strategy is not None and spec.kind == StageKind.GUARD:
                        policy = self._guard_retry_strategy.get_policy(stage_name)

                    # Always record latest output; finalized guard result may change if retry completes
                    completed[stage_name] = stage_output
                    completed_results[stage_name] = stage_result
                    self._publish_stage_wide_event(interceptor_ctx, stage_result)

                    if policy and stage_output.status == StageStatus.FAIL:
                        retry_state = guard_retry_state.setdefault(
                            stage_name, GuardRetryRuntimeState()
                        )
                        if retry_state.started_at is None:
                            retry_state.started_at = time.monotonic()

                        retry_state.attempts += 1

                        retry_hash = hash_retry_payload(stage_output, policy.hash_fields)
                        if retry_hash and retry_hash == retry_state.last_hash:
                            retry_state.stagnation_hits += 1
                        else:
                            retry_state.stagnation_hits = 0
                        retry_state.last_hash = retry_hash

                        emit_guard_retry_event(
                            "attempt",
                            guard=stage_name,
                            attempt=retry_state.attempts,
                            retry_stage=policy.retry_stage,
                            max_attempts=policy.max_attempts,
                            stagnation_hits=retry_state.stagnation_hits,
                            timeout_seconds=policy.timeout_seconds,
                        )

                        exceeded_attempts = retry_state.attempts >= policy.max_attempts
                        exceeded_stagnation = (
                            policy.stagnation_limit is not None
                            and retry_state.stagnation_hits >= policy.stagnation_limit
                        )
                        exceeded_timeout = False
                        if policy.timeout_seconds is not None and retry_state.started_at:
                            exceeded_timeout = (
                                time.monotonic() - retry_state.started_at >= policy.timeout_seconds
                            )

                        if exceeded_attempts or exceeded_stagnation or exceeded_timeout:
                            logger.error(
                                "Guard retry limits exceeded",
                                extra={
                                    "event": "guard_retry_exhausted",
                                    "guard": stage_name,
                                    "attempts": retry_state.attempts,
                                    "stagnation_hits": retry_state.stagnation_hits,
                                    "timeout": exceeded_timeout,
                                },
                            )
                            emit_guard_retry_event(
                                "exhausted",
                                guard=stage_name,
                                attempts=retry_state.attempts,
                                stagnation_hits=retry_state.stagnation_hits,
                                retry_stage=policy.retry_stage,
                                timeout_seconds=policy.timeout_seconds,
                                reason="timeout"
                                if exceeded_timeout
                                else "stagnation"
                                if exceeded_stagnation
                                else "max_attempts",
                            )
                            finalized.add(stage_name)
                        else:
                            logger.info(
                                "Scheduling guard retry",
                                extra={
                                    "event": "guard_retry",
                                    "guard": stage_name,
                                    "attempt": retry_state.attempts,
                                    "retry_stage": policy.retry_stage,
                                },
                            )
                            emit_guard_retry_event(
                                "scheduled",
                                guard=stage_name,
                                attempt=retry_state.attempts,
                                retry_stage=policy.retry_stage,
                                stagnation_hits=retry_state.stagnation_hits,
                                timeout_seconds=policy.timeout_seconds,
                            )
                            pending_guard_retries[policy.retry_stage].append(stage_name)
                            if policy.retry_stage not in active_retry_targets:
                                active_retry_targets.add(policy.retry_stage)
                                schedule_stage(policy.retry_stage)
                            else:
                                logger.debug(
                                    "Retry stage already active",
                                    extra={
                                        "event": "guard_retry_stage_active",
                                        "retry_stage": policy.retry_stage,
                                        "guard": stage_name,
                                    },
                                )
                            continue

                    if stage_output.status == StageStatus.CANCEL:
                        logger.info(
                            f"Pipeline cancelled by stage {stage_name}: {stage_output.data.get('cancel_reason', 'no reason')}",
                            extra={
                                "event": "pipeline_cancelled",
                                "stage": stage_name,
                                "reason": stage_output.data.get("cancel_reason", ""),
                                "stages_completed": list(finalized),
                            },
                        )
                        if self._cancel_token:
                            self._cancel_token.cancel(f"Cancelled by stage {stage_name}")
                        for t in active_tasks:
                            t.cancel()
                        if active_tasks:
                            await asyncio.gather(*active_tasks, return_exceptions=True)
                        raise UnifiedPipelineCancelled(
                            stage=stage_name,
                            reason=stage_output.data.get("cancel_reason", "Pipeline cancelled"),
                            results=PipelineResults(completed),
                        )

                    if stage_output.status == StageStatus.FAIL:
                        raise UnifiedStageExecutionError(
                            stage=stage_name,
                            original=RuntimeError(stage_output.error or "Stage failed"),
                        )

                    if stage_name in guard_retry_state and stage_output.status != StageStatus.FAIL:
                        recovered_state = guard_retry_state.pop(stage_name, None)
                        if recovered_state and recovered_state.attempts:
                            emit_guard_retry_event(
                                "recovered",
                                guard=stage_name,
                                attempts=recovered_state.attempts,
                            )

                    pending_guards = pending_guard_retries.pop(stage_name, [])
                    if stage_name in active_retry_targets:
                        active_retry_targets.discard(stage_name)
                    if pending_guards:
                        for guard_name in pending_guards:
                            logger.debug(
                                "Scheduling guard after retry stage completion",
                                extra={
                                    "event": "guard_retry_after_stage",
                                    "retry_stage": stage_name,
                                    "guard": guard_name,
                                },
                            )
                            schedule_stage(guard_name)

                    logger.info(
                        f"Stage {stage_name} completed with status={stage_output.status.value}, data_keys={list(stage_output.data.keys())}",
                        extra={
                            "event": "stage_completed",
                            "stage": stage_name,
                            "status": stage_output.status.value,
                            "data_keys": list(stage_output.data.keys()),
                        },
                    )

                    if stage_name not in finalized:
                        finalized.add(stage_name)
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

            self._publish_pipeline_wide_event(
                interceptor_ctx,
                completed_results,
                started_at=graph_started_at,
                status="completed",
            )

            return PipelineResults(completed)

        except UnifiedPipelineCancelled:
            self._publish_pipeline_wide_event(
                interceptor_ctx,
                completed_results,
                started_at=graph_started_at,
                status="cancelled",
            )
            raise
        except Exception:
            self._publish_pipeline_wide_event(
                interceptor_ctx,
                completed_results,
                started_at=graph_started_at,
                status="failed",
            )
            raise
        finally:
            # Always run cleanup, even on success
            await run_cleanup()
            # Clear the registry and token
            self._cleanup_registry = None
            self._cancel_token = None

    async def _execute_node(
        self,
        name: str,
        ctx: StageContext,
        completed: dict[str, StageOutput],
        shared_timer: PipelineTimer,
        interceptor_ctx: PipelineContext,
    ) -> tuple[str, StageOutput, StageResult]:
        """Execute a single stage and return its output."""
        spec = self._specs[name]

        prior_outputs = {
            dep_name: output
            for dep_name, output in completed.items()
            if dep_name in spec.dependencies
        }

        inputs = ctx.inputs
        ports = inputs.ports if inputs else None

        from stageflow.stages.inputs import create_stage_inputs

        new_inputs = create_stage_inputs(
            snapshot=ctx.snapshot,
            prior_outputs=prior_outputs,
            ports=ports,
            declared_deps=spec.dependencies,
            stage_name=name,
        )

        stage_ctx = StageContext(
            snapshot=ctx.snapshot,
            inputs=new_inputs,
            stage_name=name,
            timer=shared_timer,
            event_sink=ctx.event_sink,
            _cancellation_probe=lambda: interceptor_ctx.is_canceled
            or (self._cancel_token is not None and self._cancel_token.is_cancelled),
            _cancellation_reason_provider=lambda: interceptor_ctx.cancellation_reason
            or (self._cancel_token.reason if self._cancel_token else None),
        )

        stage_output, stage_result = await self._run_stage(spec, stage_ctx, interceptor_ctx)
        return name, stage_output, stage_result

    async def _run_stage(
        self,
        spec: UnifiedStageSpec,
        ctx: StageContext,
        interceptor_ctx: PipelineContext,
    ) -> tuple[StageOutput, StageResult]:
        """Run a stage with normalization and structured logging."""
        started_at = datetime.now(UTC)

        logger.info(
            f"Running stage: {spec.name}",
            extra={
                "event": "stage_started",
                "stage": spec.name,
                "kind": spec.kind.value if spec.kind else None,
            },
        )

        try:
            await interceptor_ctx.run_before_stage_start_hooks(
                stage_name=spec.name,
                stage_kind=spec.kind,
                stage_ctx=ctx,
            )
            ctx.raise_if_cancelled()
        except StageCancellationRequested as exc:
            ended_at = datetime.now(UTC)
            output = StageOutput.cancel(reason=exc.reason)
            output = output.with_duration(self._duration_ms(started_at, ended_at))
            result = self._stage_output_to_result(spec.name, output, started_at, ended_at)
            return output, result

        # Handle conditional stages
        if spec.conditional:
            # Check prior_outputs from dependencies for skip_reason
            skip_reason = ctx.inputs.get("skip_reason") if ctx.inputs else None
            if skip_reason:
                logger.info(
                    f"Skipping conditional stage: {spec.name}",
                    extra={
                        "event": "stage_skipped",
                        "stage": spec.name,
                        "reason": skip_reason,
                    },
                )
                # Emit stage.skipped event for observability
                if ctx.event_sink:
                    ctx.event_sink.try_emit(
                        type=f"stage.{spec.name}.skipped",
                        data={
                            "stage": spec.name,
                            "reason": skip_reason,
                            "pipeline_run_id": str(ctx.pipeline_run_id)
                            if ctx.pipeline_run_id
                            else None,
                            "request_id": str(ctx.request_id) if ctx.request_id else None,
                        },
                    )
                output = StageOutput.skip(reason=skip_reason)
                ended_at = datetime.now(UTC)
                result = self._stage_output_to_result(spec.name, output, started_at, ended_at)
                return output, result

        normalized_output: StageOutput | None = None
        exception_key = f"_interceptor.original_error.{spec.name}"

        async def run_stage() -> StageResult:
            nonlocal normalized_output

            try:
                raw_output = await spec.runner(ctx)
            except StageCancellationRequested as exc:
                ended_at = datetime.now(UTC)
                normalized_output = StageOutput.cancel(reason=exc.reason).with_duration(
                    self._duration_ms(started_at, ended_at)
                )
                return self._stage_output_to_result(
                    spec.name,
                    normalized_output,
                    started_at,
                    ended_at,
                )
            except Exception as exc:
                # Preserve original stage exception so unified error paths can
                # keep original exception types instead of coercing to RuntimeError.
                interceptor_ctx.data[exception_key] = exc
                raise

            ended_at = datetime.now(UTC)
            normalized_output = self._normalize_output(spec.name, raw_output, started_at)
            normalized_output = normalized_output.with_duration(
                self._duration_ms(started_at, ended_at)
            )
            return self._stage_output_to_result(spec.name, normalized_output, started_at, ended_at)

        try:
            stage_result = await run_with_interceptors(
                stage_name=spec.name,
                stage_run=run_stage,
                ctx=interceptor_ctx,
                interceptors=self._interceptors,
            )
            original_exc = interceptor_ctx.data.pop(exception_key, None)
            if stage_result.status == "failed" and original_exc is not None:
                raise UnifiedStageExecutionError(spec.name, original_exc)

            if normalized_output is not None:
                result = normalized_output
            else:
                result = self._stage_result_to_output(stage_result)

            if result.duration_ms is None:
                result = result.with_duration(
                    self._duration_ms(stage_result.started_at, stage_result.ended_at)
                )
            emitted_stage_result = self._stage_output_to_result(
                spec.name,
                result,
                stage_result.started_at,
                stage_result.ended_at,
            )

            duration_ms = result.duration_ms or 0

            logger.info(
                f"Stage {spec.name} completed with status={result.status.value}",
                extra={
                    "event": "stage_completed",
                    "stage": spec.name,
                    "status": result.status.value,
                    "duration_ms": duration_ms,
                },
            )

            # Emit stage.skipped event if stage returned SKIP status
            if result.status == StageStatus.SKIP and ctx.event_sink:
                ctx.event_sink.try_emit(
                    type=f"stage.{spec.name}.skipped",
                    data={
                        "stage": spec.name,
                        "reason": result.data.get("reason", "Stage returned skip"),
                        "duration_ms": duration_ms,
                        "pipeline_run_id": str(ctx.pipeline_run_id)
                        if ctx.pipeline_run_id
                        else None,
                        "request_id": str(ctx.request_id) if ctx.request_id else None,
                    },
                )

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
                return result, emitted_stage_result

            return result, emitted_stage_result

        except UnifiedStageExecutionError:
            raise
        except Exception as exc:
            ended_at = datetime.now(UTC)
            failed_result = StageResult(
                name=spec.name,
                status="failed",
                started_at=started_at,
                ended_at=ended_at,
                data={},
                error=str(exc),
            )
            self._publish_stage_wide_event(interceptor_ctx, failed_result)
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
    def _stage_output_to_result(
        name: str,
        output: StageOutput,
        started_at: datetime,
        ended_at: datetime,
    ) -> StageResult:
        status = "failed" if output.status == StageStatus.FAIL else "completed"

        return StageResult(
            name=name,
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            data=output.data,
            error=output.error,
        )

    @staticmethod
    def _coerce_result_data(data: Any) -> dict[str, Any]:
        """Coerce interceptor StageResult payloads into StageOutput-compatible dicts."""
        if isinstance(data, dict):
            return data
        if isinstance(data, StageResult):
            nested = data.data
            return nested if isinstance(nested, dict) else {}
        return {}

    @classmethod
    def _stage_result_to_output(cls, result: StageResult) -> StageOutput:
        payload = cls._coerce_result_data(result.data)
        if result.status == "failed":
            return StageOutput.fail(error=result.error or "Stage failed", data=payload)
        return StageOutput.ok(data=payload)

    @staticmethod
    def _normalize_output(
        name: str,
        raw: StageReturn,
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


__all__ = [
    "StageExecutionError",
    "StageGraph",
    "StageSpec",
    "UnifiedStageGraph",
    "UnifiedStageSpec",
    "UnifiedStageExecutionError",
    "UnifiedPipelineCancelled",
]
