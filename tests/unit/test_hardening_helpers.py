"""Tests for hardening helpers (uuid, memory, compression)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from stageflow.compression import compress
from stageflow.core import StageKind, StageOutput
from stageflow.helpers.memory_tracker import MemoryTracker, track_memory
from stageflow.helpers.run_utils import PipelineRunner
from stageflow.helpers.uuid_utils import (
    ClockSkewDetector,
    UuidCollisionMonitor,
    generate_uuid7,
)
from stageflow.pipeline import Pipeline


class SimpleStage:
    name = "simple"
    kind = StageKind.TRANSFORM

    async def execute(self, _ctx):
        return StageOutput.ok(data={"value": 42})


class TestUuidHardening:
    def test_generate_uuid7_fallback(self):
        uid = generate_uuid7()
        assert isinstance(uid, uuid4().__class__)

    def test_collision_monitor_basic(self):
        monitor = UuidCollisionMonitor(ttl_seconds=1, category="test")
        uid = uuid4()
        assert not monitor.observe(uid)
        assert monitor.observe(uid)  # collision

    def test_clock_skew_detector_no_uuid7(self):
        detector = ClockSkewDetector()
        uid = uuid4()
        assert detector.check(uid) is None  # Not UUIDv7


class TestMemoryTrackingHardening:
    @pytest.mark.asyncio
    async def test_track_memory_decorator_async(self):
        tracker = MemoryTracker(auto_start=True)

        @track_memory(label="async_work", tracker=tracker)
        async def work():
            await asyncio.sleep(0)
            return "ok"

        assert await work() == "ok"
        labels = [s.label for s in tracker.samples]
        assert "async_work:start" in labels and "async_work:end" in labels

    def test_track_memory_decorator_sync(self):
        tracker = MemoryTracker(auto_start=True)

        @track_memory(label="sync_work", tracker=tracker)
        def work():
            return "ok"

        assert work() == "ok"
        labels = [s.label for s in tracker.samples]
        assert "sync_work:start" in labels and "sync_work:end" in labels


class TestCompressionHardening:
    def test_compress_roundtrip_and_metrics(self):
        base = {"a": 1, "b": 2}
        current = {"a": 1, "b": 3, "c": 4}
        delta, metrics = compress(base, current)
        from stageflow.compression import apply_delta
        rebuilt = apply_delta(base, delta)
        assert rebuilt == current
        assert metrics.original_bytes > 0
        assert metrics.delta_bytes >= 0


class TestPipelineRunnerHardening:
    @pytest.mark.asyncio
    async def test_uuid_monitor_tracks_pipeline_run_id(self):
        monitor = UuidCollisionMonitor(ttl_seconds=1, category="pipeline")
        runner = PipelineRunner(enable_uuid_monitor=True, verbose=False, capture_events=False)
        runner._uuid_monitor = monitor

        pipeline = Pipeline().with_stage("simple", SimpleStage, StageKind.TRANSFORM)
        result = await runner.run(pipeline, input_text="test")
        assert result.success
        assert len(monitor._entries) > 0

    @pytest.mark.asyncio
    async def test_memory_tracker_emits_start_end_samples(self):
        tracker = MemoryTracker(auto_start=True)
        runner = PipelineRunner(enable_memory_tracker=True, verbose=False, capture_events=False)
        runner._memory_tracker = tracker

        pipeline = Pipeline().with_stage("simple", SimpleStage, StageKind.TRANSFORM)
        result = await runner.run(pipeline, input_text="test")
        assert result.success
        labels = [sample.label for sample in tracker.samples]
        assert any("pipeline:start" in label for label in labels)
        assert any("pipeline:end" in label for label in labels)


@pytest.fixture(autouse=True)
def stop_tracemalloc():
    yield
    import tracemalloc
    tracemalloc.stop()
