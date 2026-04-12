"""Tests for logged pipeline and subpipeline execution helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from stageflow import Pipeline, PipelineContext, StageKind, StageOutput, stage
from stageflow.core import StageContext
from stageflow.pipeline.logged import (
    LoggedSubpipelineRequest,
    run_logged_pipeline,
    run_logged_subpipeline,
    run_logged_subpipelines,
)
from stageflow.pipeline.subpipeline import SubpipelineSpawner


@dataclass
class _RecordingRunLogger:
    started: list[dict] = field(default_factory=list)
    completed: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)

    async def log_run_started(self, **kwargs):
        self.started.append(kwargs)

    async def log_run_completed(self, **kwargs):
        self.completed.append(kwargs)

    async def log_run_failed(self, **kwargs):
        self.failed.append(kwargs)


@pytest.mark.asyncio
async def test_run_logged_pipeline_logs_successful_completion() -> None:
    async def produce(ctx: StageContext) -> StageOutput:
        assert ctx.pipeline_run_id is not None
        return StageOutput.ok({"payload": {"value": 1}, "summary": "done"})

    pipeline = Pipeline.from_stages(
        stage("produce", produce, StageKind.WORK),
        name="logged_pipeline",
    )
    logger = _RecordingRunLogger()
    ctx = PipelineContext.create(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        topology="logged_pipeline",
        execution_mode="test",
        metadata={"trace_id": "trace-123"},
    )

    results = await run_logged_pipeline(pipeline, logger=logger, ctx=ctx)

    assert results.require_ok("produce").data["payload"] == {"value": 1}
    assert len(logger.started) == 1
    assert len(logger.completed) == 1
    assert logger.failed == []
    assert logger.started[0]["pipeline_run_id"] == ctx.pipeline_run_id
    assert logger.started[0]["trace_id"] == "trace-123"
    assert logger.completed[0]["status"] == "completed"
    assert logger.completed[0]["stage_results"]["produce"]["kind"] == "work"


@pytest.mark.asyncio
async def test_run_logged_pipeline_logs_cancelled_completion() -> None:
    async def cancel(_: StageContext) -> StageOutput:
        return StageOutput.cancel("stop now", {"summary": "cancelled"})

    pipeline = Pipeline.from_stages(
        stage("cancel", cancel, StageKind.GUARD),
        name="cancel_pipeline",
    )
    logger = _RecordingRunLogger()
    ctx = PipelineContext.create(pipeline_run_id=uuid4(), topology="cancel_pipeline")

    results = await run_logged_pipeline(pipeline, logger=logger, ctx=ctx)

    assert results["cancel"].status.value == "cancel"
    assert len(logger.completed) == 1
    assert logger.completed[0]["status"] == "cancelled"
    assert logger.failed == []


@pytest.mark.asyncio
async def test_run_logged_pipeline_logs_failure_and_reraises_original_error() -> None:
    async def explode(_: StageContext) -> StageOutput:
        raise ValueError("boom")

    pipeline = Pipeline.from_stages(
        stage("explode", explode, StageKind.WORK),
        name="explode_pipeline",
    )
    logger = _RecordingRunLogger()

    with pytest.raises(ValueError, match="boom"):
        await run_logged_pipeline(
            pipeline,
            logger=logger,
            ctx=PipelineContext.create(pipeline_run_id=uuid4(), topology="explode_pipeline"),
        )

    assert len(logger.started) == 1
    assert logger.completed == []
    assert len(logger.failed) == 1
    assert logger.failed[0]["stage"] == "explode"
    assert logger.failed[0]["error"] == "boom"


@pytest.mark.asyncio
async def test_run_logged_subpipeline_logs_child_run_and_preserves_lineage() -> None:
    seen_child_ctx: list[PipelineContext] = []

    async def child_stage(ctx: StageContext) -> StageOutput:
        return StageOutput.ok(
            {
                "payload": {
                    "inherited": "keep-me",
                    "request_id": str(ctx.request_id),
                },
                "summary": "child ok",
            }
        )

    pipeline = Pipeline.from_stages(
        stage("child", child_stage, StageKind.WORK),
        name="child_pipeline",
    )
    logger = _RecordingRunLogger()
    parent_ctx = PipelineContext.create(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        topology="parent_pipeline",
        execution_mode="parent_mode",
        metadata={"trace_id": "trace-child"},
        data={"parent_token": "keep-me", "drop_me": "nope"},
    )

    result = await run_logged_subpipeline(
        pipeline,
        parent_ctx=parent_ctx,
        parent_stage_id="parent_stage",
        correlation_id=uuid4(),
        logger=logger,
        spawner=SubpipelineSpawner(emit_events=False),
        inherit_data=("parent_token",),
        data_overrides={"child_only": True},
        result_stage_name="child",
        on_child_context_ready=seen_child_ctx.append,
    )

    assert result.success is True
    assert result.child_run_id is not None
    assert result.data is not None
    assert result.data["result"]["payload"]["inherited"] == "keep-me"
    assert "child" in result.data["stage_results"]
    assert len(logger.started) == 1
    assert len(logger.completed) == 1
    assert logger.failed == []
    assert logger.started[0]["parent_run_id"] == parent_ctx.pipeline_run_id
    assert logger.started[0]["parent_stage_id"] == "parent_stage"
    assert logger.started[0]["trace_id"] == "trace-child"
    assert seen_child_ctx[0].get_parent_data("parent_token") == "keep-me"
    assert seen_child_ctx[0].data["parent_token"] == "keep-me"
    assert seen_child_ctx[0].data["child_only"] is True
    assert "drop_me" not in seen_child_ctx[0].data


@pytest.mark.asyncio
async def test_run_logged_subpipeline_returns_failed_result_when_child_pipeline_errors() -> None:
    async def explode(_: StageContext) -> StageOutput:
        raise RuntimeError("child failed")

    pipeline = Pipeline.from_stages(
        stage("explode", explode, StageKind.WORK),
        name="child_failure_pipeline",
    )
    logger = _RecordingRunLogger()
    parent_ctx = PipelineContext.create(
        pipeline_run_id=uuid4(),
        topology="parent_pipeline",
    )

    result = await run_logged_subpipeline(
        pipeline,
        parent_ctx=parent_ctx,
        parent_stage_id="spawn",
        correlation_id=uuid4(),
        logger=logger,
        spawner=SubpipelineSpawner(emit_events=False),
    )

    assert result.success is False
    assert result.error == "child failed"
    assert len(logger.started) == 1
    assert len(logger.failed) == 1
    assert logger.completed == []


@pytest.mark.asyncio
async def test_run_logged_subpipelines_preserves_order_and_respects_concurrency() -> None:
    active = 0
    max_active = 0

    async def child_stage(ctx: StageContext) -> StageOutput:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await ctx.cancellation_checkpoint()
        await asyncio.sleep(0.01)
        active -= 1
        return StageOutput.ok(
            {
                "payload": {"request_id": str(ctx.request_id)},
                "summary": "ok",
            }
        )

    pipeline = Pipeline.from_stages(
        stage("child", child_stage, StageKind.WORK),
        name="parallel_child_pipeline",
    )
    parent_ctx = PipelineContext.create(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        topology="parent",
    )
    logger = _RecordingRunLogger()
    requests = [
        LoggedSubpipelineRequest(
            pipeline=pipeline,
            parent_stage_id="fanout",
            correlation_id=uuid4(),
            result_stage_name="child",
        )
        for _ in range(4)
    ]

    results = await run_logged_subpipelines(
        requests,
        parent_ctx=parent_ctx,
        logger=logger,
        spawner=SubpipelineSpawner(emit_events=False),
        concurrency=2,
    )

    assert len(results) == 4
    assert all(result.success for result in results)
    assert max_active == 2
    assert len(logger.started) == 4
    assert len(logger.completed) == 4


@pytest.mark.asyncio
async def test_run_logged_subpipelines_fail_fast_stops_starting_new_children() -> None:
    started_calls: list[str] = []

    async def ok_stage(_: StageContext) -> StageOutput:
        await asyncio.sleep(0.01)
        return StageOutput.ok({"payload": {"ok": True}, "summary": "ok"})

    async def fail_stage(_: StageContext) -> StageOutput:
        raise RuntimeError("child failed fast")

    ok_pipeline = Pipeline.from_stages(
        stage("ok", ok_stage, StageKind.WORK),
        name="ok_child",
    )
    fail_pipeline = Pipeline.from_stages(
        stage("fail", fail_stage, StageKind.WORK),
        name="fail_child",
    )
    parent_ctx = PipelineContext.create(
        pipeline_run_id=uuid4(),
        topology="parent",
    )

    def mark_started(name: str):
        return lambda _ctx: started_calls.append(name)

    requests = [
        LoggedSubpipelineRequest(
            pipeline=fail_pipeline,
            parent_stage_id="fanout",
            correlation_id=uuid4(),
            on_child_context_ready=mark_started("first"),
        ),
        LoggedSubpipelineRequest(
            pipeline=ok_pipeline,
            parent_stage_id="fanout",
            correlation_id=uuid4(),
            result_stage_name="ok",
            on_child_context_ready=mark_started("second"),
        ),
        LoggedSubpipelineRequest(
            pipeline=ok_pipeline,
            parent_stage_id="fanout",
            correlation_id=uuid4(),
            result_stage_name="ok",
            on_child_context_ready=mark_started("third"),
        ),
    ]

    results = await run_logged_subpipelines(
        requests,
        parent_ctx=parent_ctx,
        spawner=SubpipelineSpawner(emit_events=False),
        concurrency=1,
        fail_fast=True,
    )

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error == "child failed fast"
    assert started_calls == ["first"]
