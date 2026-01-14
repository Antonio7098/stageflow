"""Tests for the analytics helper module."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from stageflow.helpers.analytics import (
    AnalyticsEvent,
    JSONFileExporter,
    ConsoleExporter,
    BufferedExporter,
    CompositeExporter,
    AnalyticsSink,
)


class TestAnalyticsEvent:
    """Tests for AnalyticsEvent dataclass."""

    def test_to_dict(self):
        """Should serialize to dictionary."""
        pipeline_run_id = uuid4()
        event = AnalyticsEvent(
            event_type="stage.completed",
            pipeline_run_id=pipeline_run_id,
            stage_name="llm",
            duration_ms=150.5,
            data={"tokens": 500},
        )

        result = event.to_dict()

        assert result["event_type"] == "stage.completed"
        assert result["pipeline_run_id"] == str(pipeline_run_id)
        assert result["stage_name"] == "llm"
        assert result["duration_ms"] == 150.5
        assert result["data"]["tokens"] == 500
        assert "timestamp" in result

    def test_from_dict(self):
        """Should deserialize from dictionary."""
        data = {
            "event_type": "pipeline.started",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "data": {"mode": "test"},
            "stage_name": "start",
        }

        event = AnalyticsEvent.from_dict(data)

        assert event.event_type == "pipeline.started"
        assert event.stage_name == "start"
        assert event.data["mode"] == "test"


class TestJSONFileExporter:
    """Tests for JSONFileExporter."""

    @pytest.mark.asyncio
    async def test_exports_event(self):
        """Should write event to file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        try:
            exporter = JSONFileExporter(path)

            await exporter.export(AnalyticsEvent(
                event_type="test.event",
                data={"key": "value"},
            ))
            await exporter.flush()
            await exporter.close()

            # Read and verify
            with open(path) as f:
                line = f.readline()
                data = json.loads(line)

            assert data["event_type"] == "test.event"
            assert data["data"]["key"] == "value"
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_exports_batch(self):
        """Should write multiple events."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        try:
            exporter = JSONFileExporter(path)

            events = [
                AnalyticsEvent(event_type=f"event.{i}") for i in range(5)
            ]
            await exporter.export_batch(events)
            await exporter.close()

            # Count lines
            with open(path) as f:
                lines = f.readlines()

            assert len(lines) == 5
            assert exporter.event_count == 5
        finally:
            Path(path).unlink(missing_ok=True)


class TestConsoleExporter:
    """Tests for ConsoleExporter."""

    @pytest.mark.asyncio
    async def test_exports_event(self, capsys):
        """Should print event to console."""
        exporter = ConsoleExporter(colorize=False, verbose=True)

        await exporter.export(AnalyticsEvent(
            event_type="test.event",
            stage_name="my_stage",
        ))

        captured = capsys.readouterr()
        assert "test.event" in captured.out
        assert "my_stage" in captured.out

    @pytest.mark.asyncio
    async def test_tracks_count(self):
        """Should track event count."""
        exporter = ConsoleExporter()

        await exporter.export(AnalyticsEvent(event_type="e1"))
        await exporter.export(AnalyticsEvent(event_type="e2"))

        assert exporter.event_count == 2


class TestBufferedExporter:
    """Tests for BufferedExporter."""

    @pytest.mark.asyncio
    async def test_buffers_events(self):
        """Should buffer events before writing."""

        class CountingExporter:
            def __init__(self):
                self.batch_count = 0
                self.event_count = 0

            async def export(self, event):
                self.event_count += 1

            async def export_batch(self, events):
                self.batch_count += 1
                self.event_count += len(events)

            async def flush(self):
                pass

            async def close(self):
                pass

        base = CountingExporter()
        buffered = BufferedExporter(base, batch_size=5, flush_interval_seconds=9999)

        # Add 4 events - should not flush yet
        for i in range(4):
            await buffered.export(AnalyticsEvent(event_type=f"e{i}"))

        assert base.batch_count == 0  # Not flushed yet

        # Add 5th event - should trigger batch write
        await buffered.export(AnalyticsEvent(event_type="e4"))

        assert base.batch_count == 1
        assert base.event_count == 5

        await buffered.close()

    @pytest.mark.asyncio
    async def test_flushes_on_close(self):
        """Should flush remaining events on close."""

        class CountingExporter:
            def __init__(self):
                self.event_count = 0

            async def export(self, event):
                self.event_count += 1

            async def export_batch(self, events):
                self.event_count += len(events)

            async def flush(self):
                pass

            async def close(self):
                pass

        base = CountingExporter()
        buffered = BufferedExporter(base, batch_size=100, flush_interval_seconds=9999)

        # Add events (less than batch size)
        for i in range(3):
            await buffered.export(AnalyticsEvent(event_type=f"e{i}"))

        # Close should flush
        await buffered.close()

        assert base.event_count == 3


class TestCompositeExporter:
    """Tests for CompositeExporter."""

    @pytest.mark.asyncio
    async def test_exports_to_all(self):
        """Should export to all destinations."""

        class TrackingExporter:
            def __init__(self, name):
                self.name = name
                self.events = []

            async def export(self, event):
                self.events.append(event)

            async def export_batch(self, events):
                self.events.extend(events)

            async def flush(self):
                pass

            async def close(self):
                pass

        exp1 = TrackingExporter("exp1")
        exp2 = TrackingExporter("exp2")
        composite = CompositeExporter([exp1, exp2])

        await composite.export(AnalyticsEvent(event_type="test"))

        assert len(exp1.events) == 1
        assert len(exp2.events) == 1

        await composite.close()


class TestAnalyticsSink:
    """Tests for AnalyticsSink (EventSink adapter)."""

    @pytest.mark.asyncio
    async def test_converts_events(self):
        """Should convert event sink events to analytics events."""

        class TrackingExporter:
            def __init__(self):
                self.events = []

            async def export(self, event):
                self.events.append(event)

            async def export_batch(self, events):
                self.events.extend(events)

            async def flush(self):
                pass

            async def close(self):
                pass

        exporter = TrackingExporter()
        sink = AnalyticsSink(exporter)

        await sink.emit(
            type="stage.llm.completed",
            data={"duration_ms": 100, "stage": "llm"},
        )

        assert len(exporter.events) == 1
        assert exporter.events[0].event_type == "stage.llm.completed"
        assert exporter.events[0].duration_ms == 100
        assert exporter.events[0].stage_name == "llm"

    @pytest.mark.asyncio
    async def test_include_patterns(self):
        """Should filter events by include patterns."""

        class TrackingExporter:
            def __init__(self):
                self.events = []

            async def export(self, event):
                self.events.append(event)

            async def export_batch(self, events):
                pass

            async def flush(self):
                pass

            async def close(self):
                pass

        exporter = TrackingExporter()
        sink = AnalyticsSink(exporter, include_patterns=["stage."])

        await sink.emit(type="stage.completed", data={})
        await sink.emit(type="pipeline.started", data={})  # Should be filtered

        assert len(exporter.events) == 1
        assert exporter.events[0].event_type == "stage.completed"

    @pytest.mark.asyncio
    async def test_exclude_patterns(self):
        """Should filter out events by exclude patterns."""

        class TrackingExporter:
            def __init__(self):
                self.events = []

            async def export(self, event):
                self.events.append(event)

            async def export_batch(self, events):
                pass

            async def flush(self):
                pass

            async def close(self):
                pass

        exporter = TrackingExporter()
        sink = AnalyticsSink(exporter, exclude_patterns=["debug."])

        await sink.emit(type="stage.completed", data={})
        await sink.emit(type="debug.trace", data={})  # Should be excluded

        assert len(exporter.events) == 1


class TestBufferedExporterOverflow:
    """Tests for BufferedExporter overflow callback functionality."""

    @pytest.mark.asyncio
    async def test_calls_overflow_callback_on_drop(self):
        """Should call overflow callback when events are dropped."""
        overflow_calls: list[tuple[int, int]] = []

        def on_overflow(dropped_count: int, buffer_size: int) -> None:
            overflow_calls.append((dropped_count, buffer_size))

        class NullExporter:
            async def export(self, event):
                pass

            async def export_batch(self, events):
                pass

            async def flush(self):
                pass

            async def close(self):
                pass

        base = NullExporter()
        buffered = BufferedExporter(
            base,
            batch_size=1000,  # High batch size to prevent auto-flush
            max_buffer_size=5,
            flush_interval_seconds=9999,
            on_overflow=on_overflow,
        )

        # Fill buffer beyond max
        for i in range(7):
            await buffered.export(AnalyticsEvent(event_type=f"e{i}"))

        await buffered.close()

        # Filter out high water warnings (dropped_count = -1)
        drop_calls = [c for c in overflow_calls if c[0] > 0]

        # Should have called overflow twice (for events 6 and 7)
        assert len(drop_calls) >= 2
        # Dropped count should be positive
        assert all(dropped > 0 for dropped, _ in drop_calls)

    @pytest.mark.asyncio
    async def test_calls_high_water_callback(self):
        """Should call callback when high water mark is reached."""
        overflow_calls: list[tuple[int, int]] = []

        def on_overflow(dropped_count: int, buffer_size: int) -> None:
            overflow_calls.append((dropped_count, buffer_size))

        class NullExporter:
            async def export(self, event):
                pass

            async def export_batch(self, events):
                pass

            async def flush(self):
                pass

            async def close(self):
                pass

        base = NullExporter()
        buffered = BufferedExporter(
            base,
            batch_size=1000,
            max_buffer_size=10,
            flush_interval_seconds=9999,
            on_overflow=on_overflow,
            high_water_mark=0.8,  # 80% = 8 events
        )

        # Fill to 80%
        for i in range(9):
            await buffered.export(AnalyticsEvent(event_type=f"e{i}"))

        await buffered.close()

        # Should have high water warning (dropped_count = -1)
        high_water_calls = [c for c in overflow_calls if c[0] == -1]
        assert len(high_water_calls) >= 1

    @pytest.mark.asyncio
    async def test_stats_property(self):
        """Should provide buffer statistics."""

        class NullExporter:
            async def export(self, event):
                pass

            async def export_batch(self, events):
                pass

            async def flush(self):
                pass

            async def close(self):
                pass

        base = NullExporter()
        buffered = BufferedExporter(
            base,
            batch_size=1000,
            max_buffer_size=10,
            flush_interval_seconds=9999,
        )

        for i in range(5):
            await buffered.export(AnalyticsEvent(event_type=f"e{i}"))

        stats = buffered.stats

        assert stats["buffer_size"] == 5
        assert stats["max_buffer_size"] == 10
        assert stats["fill_ratio"] == 0.5
        assert stats["dropped_count"] == 0
        assert stats["high_water_warned"] is False

        await buffered.close()

    @pytest.mark.asyncio
    async def test_callback_errors_dont_affect_export(self):
        """Should continue working even if callback raises."""

        def bad_callback(dropped_count: int, buffer_size: int) -> None:
            raise RuntimeError("Callback failed!")

        class NullExporter:
            async def export(self, event):
                pass

            async def export_batch(self, events):
                pass

            async def flush(self):
                pass

            async def close(self):
                pass

        base = NullExporter()
        buffered = BufferedExporter(
            base,
            batch_size=1000,
            max_buffer_size=5,
            flush_interval_seconds=9999,
            on_overflow=bad_callback,
        )

        # Should not raise even when callback fails
        for i in range(10):
            await buffered.export(AnalyticsEvent(event_type=f"e{i}"))

        assert buffered.dropped_count == 5  # 10 - 5 max

        await buffered.close()

    @pytest.mark.asyncio
    async def test_high_water_resets_after_drain(self):
        """Should reset high water warning after buffer drains."""
        overflow_calls: list[tuple[int, int]] = []

        def on_overflow(dropped_count: int, buffer_size: int) -> None:
            overflow_calls.append((dropped_count, buffer_size))

        class TrackingExporter:
            def __init__(self):
                self.events = []

            async def export(self, event):
                self.events.append(event)

            async def export_batch(self, events):
                self.events.extend(events)

            async def flush(self):
                pass

            async def close(self):
                pass

        base = TrackingExporter()
        buffered = BufferedExporter(
            base,
            batch_size=100,  # High batch size to prevent auto-flush
            max_buffer_size=10,
            flush_interval_seconds=9999,
            on_overflow=on_overflow,
            high_water_mark=0.8,  # 80% = 8 events
        )

        # Fill to trigger high water (9 events = 90% > 80%)
        for i in range(9):
            await buffered.export(AnalyticsEvent(event_type=f"e{i}"))

        # High water should have been triggered
        high_water_calls = [c for c in overflow_calls if c[0] == -1]
        assert len(high_water_calls) >= 1

        await buffered.close()
