"""Unit tests for the IdempotencyInterceptor control flow."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from stageflow.pipeline.idempotency import (
    CachedStageResult,
    IdempotencyInterceptor,
    IdempotencyParamMismatch,
)
from stageflow.pipeline.interceptors import InterceptorResult
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult


def _stage_result(name: str = "work_stage", status: str = "completed") -> StageResult:
    now = datetime.now(UTC)
    return StageResult(name=name, status=status, started_at=now, ended_at=now)


def _ctx(*, key: str | None = "req-123", params: dict | None = None) -> PipelineContext:
    ctx = PipelineContext(
        pipeline_run_id=None,
        request_id=None,
        session_id=None,
        user_id=None,
        org_id=None,
        interaction_id=None,
        topology="test",
        execution_mode="test",
    )
    if key is not None:
        ctx.data["idempotency_key"] = key
    if params is not None:
        ctx.data["idempotency_params"] = params
    return ctx


@pytest.mark.asyncio
async def test_before_returns_none_when_no_key():
    interceptor = IdempotencyInterceptor()
    ctx = _ctx(key=None)

    result = await interceptor.before("stage", ctx)

    assert result is None


@pytest.mark.asyncio
async def test_before_short_circuits_on_cache_hit():
    cached = CachedStageResult(result=_stage_result())
    store = AsyncMock()
    store.get.return_value = cached
    interceptor = IdempotencyInterceptor(store=store)
    ctx = _ctx(key="req-42")

    result = await interceptor.before("stage", ctx)

    assert result is not None
    assert result.stage_ran is False
    assert result.result.name == cached.result.name
    store.get.assert_awaited_once_with("req-42")


@pytest.mark.asyncio
async def test_before_raises_on_param_mismatch():
    expected = {"amount": 100}
    cached = CachedStageResult(
        result=_stage_result(),
        params_hash=IdempotencyInterceptor._hash_params(expected),  # type: ignore[arg-type]
    )
    store = AsyncMock()
    store.get.return_value = cached
    interceptor = IdempotencyInterceptor(store=store)
    ctx = _ctx(params={"amount": 200})

    with pytest.raises(IdempotencyParamMismatch):
        await interceptor.before("stage", ctx)


@pytest.mark.asyncio
async def test_after_persists_completed_results():
    store = AsyncMock()
    interceptor = IdempotencyInterceptor(store=store, ttl_seconds=30)
    ctx = _ctx(params={"foo": "bar"})
    result = _stage_result()

    await interceptor.after("stage", result, ctx)

    store.set.assert_awaited_once()
    call = store.set.await_args
    assert call.args[0] == "req-123"
    assert isinstance(call.args[1], CachedStageResult)
    assert call.kwargs["ttl_seconds"] == 30


@pytest.mark.asyncio
async def test_after_skips_without_key():
    store = AsyncMock()
    interceptor = IdempotencyInterceptor(store=store)
    ctx = _ctx(key=None)
    result = _stage_result()

    await interceptor.after("stage", result, ctx)

    store.set.assert_not_called()


@pytest.mark.asyncio
async def test_after_skips_when_not_completed():
    store = AsyncMock()
    interceptor = IdempotencyInterceptor(store=store)
    ctx = _ctx()
    result = _stage_result(status="failed")

    await interceptor.after("stage", result, ctx)

    store.set.assert_not_called()


@pytest.mark.asyncio
async def test_before_blocks_until_inflight_result_is_cached():
    interceptor = IdempotencyInterceptor()
    ctx_primary = _ctx(key="req-concurrent", params={"amount": 100})
    ctx_duplicate = _ctx(key="req-concurrent", params={"amount": 100})
    results: dict[str, InterceptorResult | None] = {}

    async def first_invocation():
        results["first"] = await interceptor.before("stage", ctx_primary)
        await asyncio.sleep(0.05)
        await interceptor.after("stage", _stage_result(), ctx_primary)

    async def second_invocation():
        await asyncio.sleep(0.01)
        results["second"] = await interceptor.before("stage", ctx_duplicate)

    await asyncio.gather(first_invocation(), second_invocation())

    assert results["first"] is None
    assert results["second"] is not None
    assert results["second"].stage_ran is False
    assert results["second"].result.status == "completed"
