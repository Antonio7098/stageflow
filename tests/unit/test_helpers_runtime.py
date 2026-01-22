from __future__ import annotations

import asyncio
import tracemalloc
from uuid import uuid4

import pytest

from stageflow.compression import CompressionMetrics, apply_delta, compress, compute_delta
from stageflow.helpers.memory_tracker import MemoryTracker, track_memory
from stageflow.helpers.uuid_utils import UuidCollisionMonitor


class TestUuidCollisionMonitor:
    def test_detects_collision_and_notifies_listener(self):
        events: list[tuple[bool, str]] = []

        def listener(event):
            events.append((event.collision, event.category))

        monitor = UuidCollisionMonitor(ttl_seconds=1, max_entries=10, category="tool", listeners=[listener])
        value = uuid4()
        assert monitor.observe(value) is False
        assert monitor.observe(value) is True
        assert events[-1] == (True, "tool")


class TestCompressionHelpers:
    def test_compute_and_apply_delta_roundtrip(self):
        base = {"a": 1, "b": 2}
        current = {"a": 1, "b": 3, "c": 4}
        delta = compute_delta(base, current)
        assert delta == {"set": {"b": 3, "c": 4}}
        rebuilt = apply_delta(base, delta)
        assert rebuilt == current

    def test_compress_reports_metrics(self):
        base = {"foo": 1}
        current = {"foo": 2, "bar": "baz"}
        delta, metrics = compress(base, current)
        assert isinstance(metrics, CompressionMetrics)
        assert metrics.original_bytes > 0
        assert metrics.delta_bytes >= 0
        rebuilt = apply_delta(base, delta)
        assert rebuilt == current


class TestMemoryTracker:
    def test_manual_observe_records_samples(self):
        tracker = MemoryTracker(auto_start=True)
        sample = tracker.observe(label="manual")
        assert sample.label == "manual"
        assert sample.current_kb >= 0

    @pytest.mark.asyncio
    async def test_track_memory_decorator_async(self):
        tracker = MemoryTracker(auto_start=True)

        @track_memory(label="task", tracker=tracker)
        async def do_work():
            await asyncio.sleep(0)
            return 42

        result = await do_work()
        assert result == 42
        labels = [sample.label for sample in tracker.samples]
        assert "task:start" in labels and "task:end" in labels

    def test_track_memory_decorator_sync(self):
        tracker = MemoryTracker(auto_start=True)

        @track_memory(label="sync_task", tracker=tracker)
        def do_work_sync():
            return "ok"

        assert do_work_sync() == "ok"
        labels = [sample.label for sample in tracker.samples]
        assert "sync_task:start" in labels and "sync_task:end" in labels


@pytest.fixture(autouse=True)
def stop_tracemalloc():
    yield
    tracemalloc.stop()
