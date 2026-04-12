"""Logged pipeline and subpipeline execution helpers.

This module provides a framework-native runtime surface for the production
wrapper pattern many host applications need:

- create or reuse a canonical ``PipelineContext``
- log run start/completion/failure through ``PipelineRunLogger``
- preserve wide-event configuration in one place
- run child pipelines with ``SubpipelineSpawner`` while preserving lineage
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from stageflow.core import StageContext
from stageflow.observability import NoOpPipelineRunLogger, PipelineRunLogger, WideEventEmitter
from stageflow.pipeline.dag import UnifiedPipelineCancelled, UnifiedStageExecutionError
from stageflow.pipeline.pipeline import Pipeline
from stageflow.pipeline.results import PipelineResults
from stageflow.pipeline.subpipeline import (
    SubpipelineResult,
    SubpipelineSpawner,
    get_subpipeline_spawner,
)
from stageflow.stages.context import PipelineContext
from stageflow.stages.payloads import summary_from_output


@dataclass(frozen=True, slots=True)
class LoggedSubpipelineRequest:
    """Configuration for one logged child pipeline run."""

    pipeline: Pipeline
    correlation_id: UUID
    parent_stage_id: str
    topology: str | None = None
    execution_mode: str | None = None
    inherit_data: bool | Iterable[str] = True
    data_overrides: dict[str, Any] | None = None
    result_stage_name: str | None = None
    result_data_builder: Callable[[PipelineResults], dict[str, Any]] | None = None
    on_child_context_ready: Callable[[PipelineContext], None] | None = None


def _run_logger_kwargs(ctx: PipelineContext) -> dict[str, Any]:
    """Build common correlation kwargs for run logger calls."""
    return {
        "request_id": ctx.request_id,
        "session_id": ctx.session_id,
        "trace_id": ctx.metadata.get("trace_id"),
        "parent_run_id": ctx.parent_run_id,
        "parent_stage_id": ctx.parent_stage_id,
        "correlation_id": ctx.correlation_id,
    }


def _stage_summaries(pipeline: Pipeline, results: PipelineResults) -> dict[str, Any]:
    """Build serializable stage summaries for run logging."""
    summaries: dict[str, Any] = {}
    for stage_name, output in results.items():
        kind = pipeline.stages.get(stage_name).kind.value if stage_name in pipeline.stages else None
        summaries[stage_name] = {
            "kind": kind,
            **summary_from_output(output),
        }
    return summaries


def _coerce_parent_pipeline_context(
    parent_ctx: PipelineContext | StageContext,
) -> PipelineContext:
    """Normalize parent execution context for subpipeline orchestration."""
    if isinstance(parent_ctx, PipelineContext):
        return parent_ctx
    return PipelineContext.from_snapshot(
        parent_ctx.snapshot,
        event_sink=parent_ctx.event_sink,
        ports=parent_ctx.inputs.ports,
        service="pipeline",
        data={},
    )


async def run_logged_pipeline(
    pipeline: Pipeline,
    *,
    logger: PipelineRunLogger | None = None,
    ctx: PipelineContext | None = None,
    interceptors: list[Any] | None = None,
    guard_retry_strategy: Any = None,
    emit_stage_wide_events: bool = True,
    emit_pipeline_wide_event: bool = True,
    wide_event_emitter: WideEventEmitter | None = None,
    on_context_ready: Callable[[PipelineContext], None] | None = None,
    **context_kwargs: Any,
) -> PipelineResults:
    """Run a pipeline with framework-managed lifecycle logging."""
    if ctx is not None and context_kwargs:
        raise ValueError("Pass either ctx or PipelineContext keyword fields, not both")

    if ctx is None:
        if "topology" not in context_kwargs:
            context_kwargs["topology"] = pipeline.name
        ctx = PipelineContext.create(**context_kwargs)

    active_logger = logger or NoOpPipelineRunLogger()
    if on_context_ready is not None:
        on_context_ready(ctx)

    started_at = datetime.now(UTC)
    await active_logger.log_run_started(
        pipeline_run_id=ctx.pipeline_run_id,
        pipeline_name=pipeline.name,
        topology=ctx.topology or pipeline.name,
        execution_mode=ctx.execution_mode,
        user_id=ctx.user_id,
        **_run_logger_kwargs(ctx),
    )

    try:
        results = await pipeline.run(
            ctx,
            interceptors=interceptors,
            guard_retry_strategy=guard_retry_strategy,
            emit_stage_wide_events=emit_stage_wide_events,
            emit_pipeline_wide_event=emit_pipeline_wide_event,
            wide_event_emitter=wide_event_emitter,
        )
    except UnifiedPipelineCancelled as exc:
        finished_at = datetime.now(UTC)
        await active_logger.log_run_completed(
            pipeline_run_id=ctx.pipeline_run_id,
            pipeline_name=pipeline.name,
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            status="cancelled",
            stage_results=_stage_summaries(pipeline, exc.results),
            **_run_logger_kwargs(ctx),
        )
        return exc.results
    except UnifiedStageExecutionError as exc:
        await active_logger.log_run_failed(
            pipeline_run_id=ctx.pipeline_run_id,
            pipeline_name=pipeline.name,
            error=str(exc.original),
            stage=exc.stage,
            **_run_logger_kwargs(ctx),
        )
        raise exc.original from exc
    except Exception as exc:
        await active_logger.log_run_failed(
            pipeline_run_id=ctx.pipeline_run_id,
            pipeline_name=pipeline.name,
            error=str(exc),
            stage=None,
            **_run_logger_kwargs(ctx),
        )
        raise

    finished_at = datetime.now(UTC)
    await active_logger.log_run_completed(
        pipeline_run_id=ctx.pipeline_run_id,
        pipeline_name=pipeline.name,
        duration_ms=int((finished_at - started_at).total_seconds() * 1000),
        status="completed",
        stage_results=_stage_summaries(pipeline, results),
        **_run_logger_kwargs(ctx),
    )
    return results


async def run_logged_subpipeline(
    pipeline: Pipeline,
    *,
    parent_ctx: PipelineContext | StageContext,
    parent_stage_id: str,
    correlation_id: UUID,
    logger: PipelineRunLogger | None = None,
    spawner: SubpipelineSpawner | None = None,
    interceptors: list[Any] | None = None,
    guard_retry_strategy: Any = None,
    emit_stage_wide_events: bool = True,
    emit_pipeline_wide_event: bool = True,
    wide_event_emitter: WideEventEmitter | None = None,
    topology: str | None = None,
    execution_mode: str | None = None,
    inherit_data: bool | Iterable[str] = True,
    data_overrides: dict[str, Any] | None = None,
    result_stage_name: str | None = None,
    result_data_builder: Callable[[PipelineResults], dict[str, Any]] | None = None,
    on_child_context_ready: Callable[[PipelineContext], None] | None = None,
) -> SubpipelineResult:
    """Spawn a logged child pipeline run with preserved parent/child lineage."""
    active_logger = logger or NoOpPipelineRunLogger()
    active_spawner = spawner or get_subpipeline_spawner()
    pipeline_ctx = _coerce_parent_pipeline_context(parent_ctx)

    async def runner(child_ctx: PipelineContext) -> dict[str, Any]:
        if on_child_context_ready is not None:
            on_child_context_ready(child_ctx)
        started_at = datetime.now(UTC)
        await active_logger.log_run_started(
            pipeline_run_id=child_ctx.pipeline_run_id,
            pipeline_name=pipeline.name,
            topology=child_ctx.topology or pipeline.name,
            execution_mode=child_ctx.execution_mode,
            user_id=child_ctx.user_id,
            **_run_logger_kwargs(child_ctx),
        )
        try:
            results = await pipeline.run(
                child_ctx,
                interceptors=interceptors,
                guard_retry_strategy=guard_retry_strategy,
                emit_stage_wide_events=emit_stage_wide_events,
                emit_pipeline_wide_event=emit_pipeline_wide_event,
                wide_event_emitter=wide_event_emitter,
            )
        except UnifiedPipelineCancelled as exc:
            finished_at = datetime.now(UTC)
            await active_logger.log_run_completed(
                pipeline_run_id=child_ctx.pipeline_run_id,
                pipeline_name=pipeline.name,
                duration_ms=int((finished_at - started_at).total_seconds() * 1000),
                status="cancelled",
                stage_results=_stage_summaries(pipeline, exc.results),
                **_run_logger_kwargs(child_ctx),
            )
            return {"stage_results": _stage_summaries(pipeline, exc.results)}
        except UnifiedStageExecutionError as exc:
            await active_logger.log_run_failed(
                pipeline_run_id=child_ctx.pipeline_run_id,
                pipeline_name=pipeline.name,
                error=str(exc.original),
                stage=exc.stage,
                **_run_logger_kwargs(child_ctx),
            )
            raise exc.original from exc
        except Exception as exc:
            await active_logger.log_run_failed(
                pipeline_run_id=child_ctx.pipeline_run_id,
                pipeline_name=pipeline.name,
                error=str(exc),
                stage=None,
                **_run_logger_kwargs(child_ctx),
            )
            raise

        finished_at = datetime.now(UTC)
        stage_results = _stage_summaries(pipeline, results)
        await active_logger.log_run_completed(
            pipeline_run_id=child_ctx.pipeline_run_id,
            pipeline_name=pipeline.name,
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            status="completed",
            stage_results=stage_results,
            **_run_logger_kwargs(child_ctx),
        )
        payload: dict[str, Any] = {"stage_results": stage_results}
        if result_data_builder is not None:
            payload.update(result_data_builder(results))
        elif result_stage_name is not None:
            payload["result"] = results.require_ok(result_stage_name).data
        return payload

    return await active_spawner.spawn(
        pipeline_name=pipeline.name,
        ctx=pipeline_ctx,
        correlation_id=correlation_id,
        parent_stage_id=parent_stage_id,
        runner=runner,
        topology=topology or pipeline.name,
        execution_mode=execution_mode,
        inherit_data=inherit_data,
        data_overrides=data_overrides,
    )


async def run_logged_subpipelines(
    requests: Iterable[LoggedSubpipelineRequest],
    *,
    parent_ctx: PipelineContext | StageContext,
    logger: PipelineRunLogger | None = None,
    spawner: SubpipelineSpawner | None = None,
    interceptors: list[Any] | None = None,
    guard_retry_strategy: Any = None,
    emit_stage_wide_events: bool = True,
    emit_pipeline_wide_event: bool = True,
    wide_event_emitter: WideEventEmitter | None = None,
    concurrency: int | None = None,
    fail_fast: bool = False,
) -> list[SubpipelineResult]:
    """Run multiple logged child pipelines with bounded concurrency.

    Results preserve input order. When ``fail_fast`` is enabled, no new child
    runs are started after the first failed result or orchestration exception,
    though already-running child runs are allowed to finish.
    """
    request_list = list(requests)
    if not request_list:
        return []

    if concurrency is None:
        concurrency = len(request_list)
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")

    results: list[SubpipelineResult | None] = [None] * len(request_list)
    next_index = 0
    index_lock = asyncio.Lock()
    stop_requested = asyncio.Event()
    raised: list[BaseException] = []

    async def worker() -> None:
        nonlocal next_index
        while True:
            async with index_lock:
                if stop_requested.is_set() and fail_fast:
                    return
                if next_index >= len(request_list):
                    return
                current_index = next_index
                next_index += 1
            request = request_list[current_index]
            try:
                result = await run_logged_subpipeline(
                    request.pipeline,
                    parent_ctx=parent_ctx,
                    parent_stage_id=request.parent_stage_id,
                    correlation_id=request.correlation_id,
                    logger=logger,
                    spawner=spawner,
                    interceptors=interceptors,
                    guard_retry_strategy=guard_retry_strategy,
                    emit_stage_wide_events=emit_stage_wide_events,
                    emit_pipeline_wide_event=emit_pipeline_wide_event,
                    wide_event_emitter=wide_event_emitter,
                    topology=request.topology,
                    execution_mode=request.execution_mode,
                    inherit_data=request.inherit_data,
                    data_overrides=request.data_overrides,
                    result_stage_name=request.result_stage_name,
                    result_data_builder=request.result_data_builder,
                    on_child_context_ready=request.on_child_context_ready,
                )
                results[current_index] = result
                if fail_fast and not result.success:
                    stop_requested.set()
            except BaseException as exc:
                raised.append(exc)
                stop_requested.set()
                return

    worker_count = min(concurrency, len(request_list))
    await asyncio.gather(*(worker() for _ in range(worker_count)))

    if raised:
        raise raised[0]

    return [result for result in results if result is not None]


__all__ = [
    "LoggedSubpipelineRequest",
    "run_logged_pipeline",
    "run_logged_subpipeline",
    "run_logged_subpipelines",
]
