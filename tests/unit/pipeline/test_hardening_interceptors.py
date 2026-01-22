"""Tests for hardening interceptors (immutability, context size)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from stageflow.context import ContextSnapshot, RunIdentity
from stageflow.pipeline.interceptors_hardening import (
    ContextSizeInterceptor,
    ImmutabilityInterceptor,
)
from stageflow.stages.result import StageResult


@dataclass
class DummyContext:
    """Minimal context stub exposing snapshot/data/event_sink interfaces."""

    snapshot: ContextSnapshot | None
    data: dict[str, Any]
    event_sink: Any = field(default_factory=MagicMock)
    metrics: list[tuple[str, int, dict[str, str]]] = field(default_factory=list)

    def record_metric(self, name: str, value: int, tags: dict[str, str]) -> None:
        self.metrics.append((name, value, tags))


def make_stage_result(name: str, status: str = "completed") -> StageResult:
    now = datetime.now(UTC)
    return StageResult(name=name, status=status, started_at=now, ended_at=now)


class TestImmutabilityInterceptor:
    @pytest.fixture
    def ctx(self):
        snapshot = ContextSnapshot(
            run_id=RunIdentity(),
            topology="test",
            metadata={"key": "initial_value"},
        )
        return DummyContext(snapshot=snapshot, data={}, event_sink=MagicMock())

    @pytest.mark.asyncio
    async def test_detects_snapshot_mutation(self, ctx):
        interceptor = ImmutabilityInterceptor(crash_on_violation=True)
        stage_name = "mutating_stage"

        await interceptor.before(stage_name, ctx)

        # Simulate mutation
        ctx.snapshot.metadata["key"] = "mutated_value"

        result = make_stage_result(stage_name)

        with pytest.raises(RuntimeError, match="Immutability violation"):
            await interceptor.after(stage_name, result, ctx)

    @pytest.mark.asyncio
    async def test_passes_when_no_mutation(self, ctx):
        interceptor = ImmutabilityInterceptor(crash_on_violation=True)
        stage_name = "clean_stage"

        await interceptor.before(stage_name, ctx)
        # No mutation
        result = make_stage_result(stage_name)
        await interceptor.after(stage_name, result, ctx)

    @pytest.mark.asyncio
    async def test_logs_instead_of_crash_if_configured(self, ctx, caplog):
        interceptor = ImmutabilityInterceptor(crash_on_violation=False)
        stage_name = "mutating_stage_log"

        await interceptor.before(stage_name, ctx)
        ctx.snapshot.metadata["key"] = "mutated"
        result = make_stage_result(stage_name)

        with caplog.at_level("ERROR", logger="stageflow.hardening"):
            await interceptor.after(stage_name, result, ctx)

        assert "Immutability violation" in caplog.text


class TestContextSizeInterceptor:
    @pytest.fixture
    def ctx(self):
        snapshot = ContextSnapshot(
            run_id=RunIdentity(),
            input_text="A" * 1000,  # ~1KB
        )
        return DummyContext(
            snapshot=snapshot,
            data={"temp": "B" * 500},
            event_sink=MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_warns_on_size_threshold(self, ctx, caplog):
        # Set low threshold to trigger warning
        interceptor = ContextSizeInterceptor(max_size_bytes=100)
        stage_name = "fat_context_stage"

        with caplog.at_level("WARNING", logger="stageflow.hardening"):
            await interceptor.before(stage_name, ctx)

        assert "Context size warning" in caplog.text
        assert "exceeds limit" in caplog.text

    @pytest.mark.asyncio
    async def test_warns_on_growth(self, ctx, caplog):
        interceptor = ContextSizeInterceptor(warn_on_growth_bytes=100)
        stage_name = "growing_stage"

        await interceptor.before(stage_name, ctx)

        # Grow context significantly
        ctx.data["huge_output"] = "C" * 2000

        result = make_stage_result(stage_name)

        with caplog.at_level("WARNING", logger="stageflow.hardening"):
            await interceptor.after(stage_name, result, ctx)

        assert "Significant context growth" in caplog.text
