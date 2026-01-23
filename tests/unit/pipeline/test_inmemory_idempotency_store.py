"""Unit tests for the InMemoryIdempotencyStore implementation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from stageflow.pipeline.idempotency import CachedStageResult, InMemoryIdempotencyStore
from stageflow.stages.result import StageResult


def _stage_result() -> StageResult:
    now = datetime.now(UTC)
    return StageResult(name="stage", status="completed", started_at=now, ended_at=now)


@pytest.mark.asyncio
async def test_store_gets_and_sets_values():
    store = InMemoryIdempotencyStore()
    key = "req-1"
    result = CachedStageResult(result=_stage_result())

    await store.set(key, result, ttl_seconds=60)

    fetched = await store.get(key)
    assert fetched is not None
    assert fetched.result.name == "stage"


@pytest.mark.asyncio
async def test_store_expires_entries(monkeypatch):
    store = InMemoryIdempotencyStore()
    key = "req-2"
    result = CachedStageResult(result=_stage_result())

    base_time = 1_000_000.0
    monkeypatch.setattr("stageflow.pipeline.idempotency.time.time", lambda: base_time)
    await store.set(key, result, ttl_seconds=5)

    assert await store.get(key) is not None

    monkeypatch.setattr("stageflow.pipeline.idempotency.time.time", lambda: base_time + 6)
    assert await store.get(key) is None


@pytest.mark.asyncio
async def test_delete_removes_entry():
    store = InMemoryIdempotencyStore()
    key = "req-3"
    result = CachedStageResult(result=_stage_result())

    await store.set(key, result)
    await store.delete(key)

    fetched = await store.get(key)
    assert fetched is None
