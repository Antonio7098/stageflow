"""Tests for BackpressureAwareEventSink."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from stageflow.events.sink import (
    BackpressureAwareEventSink,
    BackpressureMetrics,
    LoggingEventSink,
    NoOpEventSink,
)


class TestBackpressureMetrics:
    """Tests for BackpressureMetrics."""

    def test_initial_state(self):
        """Metrics start at zero."""
        metrics = BackpressureMetrics()
        assert metrics.emitted == 0
        assert metrics.dropped == 0
        assert metrics.queue_full_count == 0
        assert metrics.drop_rate == 0.0

    def test_record_emit(self):
        """record_emit increments emitted count."""
        metrics = BackpressureMetrics()
        metrics.record_emit()
        assert metrics.emitted == 1
        assert metrics.last_emit_time > 0

    def test_record_drop(self):
        """record_drop increments dropped and queue_full_count."""
        metrics = BackpressureMetrics()
        metrics.record_drop()
        assert metrics.dropped == 1
        assert metrics.queue_full_count == 1
        assert metrics.last_drop_time > 0

    def test_drop_rate_calculation(self):
        """drop_rate calculates percentage correctly."""
        metrics = BackpressureMetrics()
        # 8 emitted, 2 dropped = 20% drop rate
        for _ in range(8):
            metrics.record_emit()
        for _ in range(2):
            metrics.record_drop()
        assert metrics.drop_rate == 20.0

    def test_drop_rate_zero_total(self):
        """drop_rate returns 0 when no events."""
        metrics = BackpressureMetrics()
        assert metrics.drop_rate == 0.0

    def test_to_dict(self):
        """to_dict returns all metrics."""
        metrics = BackpressureMetrics()
        metrics.record_emit()
        metrics.record_drop()
        result = metrics.to_dict()
        assert result["emitted"] == 1
        assert result["dropped"] == 1
        assert result["queue_full_count"] == 1
        assert result["drop_rate_percent"] == 50.0
        assert "last_emit_time" in result
        assert "last_drop_time" in result


class TestBackpressureAwareEventSink:
    """Tests for BackpressureAwareEventSink."""

    @pytest.mark.asyncio
    async def test_basic_emit(self):
        """Events are emitted to downstream sink."""
        downstream = AsyncMock()
        downstream.emit = AsyncMock()
        sink = BackpressureAwareEventSink(downstream, max_queue_size=10)

        await sink.start()
        try:
            await sink.emit(type="test.event", data={"key": "value"})
            # Give worker time to process
            await asyncio.sleep(0.2)
            downstream.emit.assert_called_once_with(type="test.event", data={"key": "value"})
        finally:
            await sink.stop()

    @pytest.mark.asyncio
    async def test_try_emit_success(self):
        """try_emit returns True when queue has space."""
        sink = BackpressureAwareEventSink(NoOpEventSink(), max_queue_size=10)
        await sink.start()
        try:
            result = sink.try_emit(type="test.event", data={"key": "value"})
            assert result is True
            assert sink.metrics.emitted == 1
            assert sink.metrics.dropped == 0
        finally:
            await sink.stop()

    @pytest.mark.asyncio
    async def test_try_emit_backpressure(self):
        """try_emit returns False and records drop when queue is full."""
        # Create a slow downstream that blocks
        slow_downstream = AsyncMock()
        slow_downstream.emit = AsyncMock(side_effect=lambda **_: asyncio.sleep(10))

        sink = BackpressureAwareEventSink(slow_downstream, max_queue_size=2)
        await sink.start()
        try:
            # Fill the queue
            sink.try_emit(type="event.1", data=None)
            sink.try_emit(type="event.2", data=None)

            # This should be dropped
            result = sink.try_emit(type="event.3", data=None)
            assert result is False
            assert sink.metrics.dropped == 1
            assert sink.metrics.queue_full_count == 1
        finally:
            await sink.stop(drain=False)

    @pytest.mark.asyncio
    async def test_on_drop_callback(self):
        """on_drop callback is called when event is dropped."""
        dropped_events: list[tuple[str, Any]] = []

        def on_drop(event_type: str, data: dict[str, Any] | None) -> None:
            dropped_events.append((event_type, data))

        slow_downstream = AsyncMock()
        slow_downstream.emit = AsyncMock(side_effect=lambda **_: asyncio.sleep(10))

        sink = BackpressureAwareEventSink(slow_downstream, max_queue_size=1, on_drop=on_drop)
        await sink.start()
        try:
            sink.try_emit(type="event.1", data={"a": 1})
            sink.try_emit(type="event.2", data={"b": 2})  # Should be dropped

            assert len(dropped_events) == 1
            assert dropped_events[0] == ("event.2", {"b": 2})
        finally:
            await sink.stop(drain=False)

    @pytest.mark.asyncio
    async def test_graceful_shutdown_drains_queue(self):
        """stop() with drain=True processes remaining events."""
        events_received: list[str] = []

        class CollectorSink:
            async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:  # noqa: ARG002
                events_received.append(type)

            def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None:  # noqa: ARG002
                events_received.append(type)

        sink = BackpressureAwareEventSink(CollectorSink(), max_queue_size=100)
        await sink.start()

        # Queue some events
        for i in range(5):
            sink.try_emit(type=f"event.{i}", data=None)

        # Stop with drain
        await sink.stop(drain=True, timeout=5.0)

        # All events should have been processed
        assert len(events_received) == 5

    @pytest.mark.asyncio
    async def test_queue_size_property(self):
        """queue_size returns current queue size."""
        slow_downstream = AsyncMock()
        slow_downstream.emit = AsyncMock(side_effect=lambda **_: asyncio.sleep(10))

        sink = BackpressureAwareEventSink(slow_downstream, max_queue_size=10)
        await sink.start()
        try:
            assert sink.queue_size == 0
            sink.try_emit(type="event.1", data=None)
            assert sink.queue_size >= 0  # May have been processed already
        finally:
            await sink.stop(drain=False)

    @pytest.mark.asyncio
    async def test_is_running_property(self):
        """is_running reflects worker state."""
        sink = BackpressureAwareEventSink(NoOpEventSink(), max_queue_size=10)
        assert sink.is_running is False

        await sink.start()
        assert sink.is_running is True

        await sink.stop()
        assert sink.is_running is False

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        """Multiple start() calls are safe."""
        sink = BackpressureAwareEventSink(NoOpEventSink(), max_queue_size=10)
        await sink.start()
        await sink.start()  # Should not raise
        assert sink.is_running is True
        await sink.stop()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self):
        """Multiple stop() calls are safe."""
        sink = BackpressureAwareEventSink(NoOpEventSink(), max_queue_size=10)
        await sink.start()
        await sink.stop()
        await sink.stop()  # Should not raise
        assert sink.is_running is False

    @pytest.mark.asyncio
    async def test_auto_start_on_emit(self):
        """emit() auto-starts the worker if not running."""
        sink = BackpressureAwareEventSink(NoOpEventSink(), max_queue_size=10)
        assert sink.is_running is False

        await sink.emit(type="test.event", data=None)
        assert sink.is_running is True

        await sink.stop()

    @pytest.mark.asyncio
    async def test_downstream_error_handling(self):
        """Errors from downstream are logged but don't crash worker."""
        error_downstream = AsyncMock()
        error_downstream.emit = AsyncMock(side_effect=Exception("Downstream error"))

        sink = BackpressureAwareEventSink(error_downstream, max_queue_size=10)
        await sink.start()
        try:
            sink.try_emit(type="event.1", data=None)
            await asyncio.sleep(0.2)  # Give worker time to process

            # Worker should still be running
            assert sink.is_running is True

            # Should be able to emit more events
            sink.try_emit(type="event.2", data=None)
            await asyncio.sleep(0.2)

            # Both events should have been attempted
            assert error_downstream.emit.call_count == 2
        finally:
            await sink.stop()

    @pytest.mark.asyncio
    async def test_high_throughput_stress(self):
        """Sink handles high event throughput without crashing."""
        events_received = 0

        class CounterSink:
            async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:  # noqa: ARG002
                nonlocal events_received
                events_received += 1

            def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None:  # noqa: ARG002
                nonlocal events_received
                events_received += 1

        sink = BackpressureAwareEventSink(CounterSink(), max_queue_size=100)
        await sink.start()
        try:
            # Emit 1000 events rapidly
            for i in range(1000):
                sink.try_emit(type=f"event.{i}", data={"index": i})

            # Wait for processing
            await asyncio.sleep(1.0)

            # Check metrics
            total = sink.metrics.emitted + sink.metrics.dropped
            assert total == 1000
            # Some events may have been dropped due to backpressure
            assert sink.metrics.emitted > 0
        finally:
            await sink.stop(drain=True, timeout=2.0)

    @pytest.mark.asyncio
    async def test_default_downstream_is_logging_sink(self):
        """Default downstream is LoggingEventSink."""
        sink = BackpressureAwareEventSink(max_queue_size=10)
        assert isinstance(sink._downstream, LoggingEventSink)
        await sink.stop()
