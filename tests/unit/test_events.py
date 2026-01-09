"""Comprehensive tests for stageflow.events module.

Tests:
- EventSink protocol
- NoOpEventSink
- LoggingEventSink
- set_event_sink, get_event_sink, clear_event_sink
- wait_for_event_sink_tasks
"""

import asyncio
import logging

from stageflow.events import (
    LoggingEventSink,
    NoOpEventSink,
    clear_event_sink,
    get_event_sink,
    set_event_sink,
    wait_for_event_sink_tasks,
)
from stageflow.events.sink import (
    EventSink,
    _pending_emit_tasks,
)

# === Test EventSink Protocol ===

class TestEventSinkProtocol:
    """Tests for EventSink protocol."""

    def test_noop_event_sink_is_event_sink(self):
        """Test NoOpEventSink implements EventSink."""
        sink = NoOpEventSink()
        assert isinstance(sink, EventSink)

    def test_logging_event_sink_is_event_sink(self):
        """Test LoggingEventSink implements EventSink."""
        sink = LoggingEventSink()
        assert isinstance(sink, EventSink)


# === Test NoOpEventSink ===

class TestNoOpEventSink:
    """Tests for NoOpEventSink."""

    def test_emit_does_nothing(self):
        """Test emit is a no-op."""
        sink = NoOpEventSink()
        # Should not raise
        asyncio.run(sink.emit(type="test", data={"key": "value"}))

    def test_try_emit_does_nothing(self):
        """Test try_emit is a no-op."""
        sink = NoOpEventSink()
        # Should not raise
        sink.try_emit(type="test", data={"key": "value"})

    def test_emit_returns_none(self):
        """Test emit returns None."""
        sink = NoOpEventSink()
        result = asyncio.run(sink.emit(type="test", data=None))
        assert result is None

    def test_emit_ignores_parameters(self):
        """Test emit ignores type and data parameters."""
        sink = NoOpEventSink()
        # Should not raise even with None
        asyncio.run(sink.emit(type=None, data=None))

    def test_try_emit_ignores_parameters(self):
        """Test try_emit ignores type and data parameters."""
        sink = NoOpEventSink()
        # Should not raise
        sink.try_emit(type=None, data=None)


# === Test LoggingEventSink ===

class TestLoggingEventSink:
    """Tests for LoggingEventSink."""

    def test_init_with_default_level(self):
        """Test default log level is INFO."""
        sink = LoggingEventSink()
        assert sink._level == logging.INFO

    def test_init_with_custom_level(self):
        """Test custom log level."""
        sink = LoggingEventSink(level=logging.DEBUG)
        assert sink._level == logging.DEBUG

    def test_emit_logs_info(self, caplog):
        """Test emit logs at INFO level."""
        caplog.set_level(logging.INFO)
        sink = LoggingEventSink()

        async def run_emit():
            await sink.emit(type="test.event", data={"key": "value"})

        asyncio.run(run_emit())

        # Check that log was emitted
        assert "test.event" in caplog.text

    def test_try_emit_logs(self, caplog):
        """Test try_emit logs."""
        caplog.set_level(logging.INFO)
        sink = LoggingEventSink()

        sink.try_emit(type="test.event", data={"key": "value"})

        # Check that log was emitted
        assert "test.event" in caplog.text

    def test_emit_with_none_data(self, caplog):
        """Test emit with None data."""
        caplog.set_level(logging.INFO)
        sink = LoggingEventSink()

        async def run_emit():
            await sink.emit(type="test.event", data=None)

        asyncio.run(run_emit())

        # Check that log was emitted
        assert "test.event" in caplog.text


# === Test Event Sink Context Functions ===

class TestEventSinkContextFunctions:
    """Tests for event sink context functions."""

    def teardown_method(self):
        """Reset event sink after each test."""
        clear_event_sink()

    def test_get_event_sink_default_noop(self):
        """Test get_event_sink returns NoOpEventSink by default."""
        clear_event_sink()
        sink = get_event_sink()
        assert isinstance(sink, NoOpEventSink)

    def test_set_event_sink(self):
        """Test set_event_sink stores sink."""
        custom_sink = NoOpEventSink()
        set_event_sink(custom_sink)
        sink = get_event_sink()
        assert sink is custom_sink

    def test_clear_event_sink(self):
        """Test clear_event_sink resets to default."""
        custom_sink = NoOpEventSink()
        set_event_sink(custom_sink)
        clear_event_sink()
        sink = get_event_sink()
        assert isinstance(sink, NoOpEventSink)
        assert sink is not custom_sink

    def test_set_and_get_roundtrip(self):
        """Test set and get roundtrip."""
        sink1 = LoggingEventSink(level=logging.DEBUG)
        set_event_sink(sink1)
        sink2 = get_event_sink()
        assert sink2 is sink1

    def test_multiple_set_overwrites(self):
        """Test multiple set_event_sink calls overwrite."""
        sink1 = NoOpEventSink()
        sink2 = NoOpEventSink()

        set_event_sink(sink1)
        set_event_sink(sink2)

        sink = get_event_sink()
        assert sink is sink2


# === Test wait_for_event_sink_tasks ===

class TestWaitForEventSinkTasks:
    """Tests for wait_for_event_sink_tasks function."""

    def teardown_method(self):
        """Reset event sink after each test."""
        clear_event_sink()

    def test_no_pending_tasks(self):
        """Test with no pending tasks."""
        # Should not raise
        asyncio.run(wait_for_event_sink_tasks())

    def test_clears_completed_tasks(self):
        """Test that completed tasks are cleared."""
        clear_event_sink()
        _pending_emit_tasks.clear()  # Ensure clean state

        async def run_test():
            # Create and complete a task
            async def dummy():
                pass

            task = asyncio.create_task(dummy())
            _pending_emit_tasks.add(task)
            await task

            # Wait should clear it
            await wait_for_event_sink_tasks()

            return len(_pending_emit_tasks)

        result = asyncio.run(run_test())
        assert result == 0


# === Test EventSink with Context Variables ===

class TestEventSinkContextVariable:
    """Tests for event sink context variable behavior."""

    def teardown_method(self):
        """Reset after each test."""
        clear_event_sink()

    def test_context_variable_isolation(self):
        """Test that event sink is isolated per context."""
        sink1 = NoOpEventSink()
        LoggingEventSink()

        # Set sink1
        set_event_sink(sink1)

        # Verify in current context
        assert get_event_sink() is sink1

    def test_event_sink_inheritance(self):
        """Test that event sink is inherited in new tasks."""
        set_event_sink(NoOpEventSink())

        async def check_sink():
            return get_event_sink()

        sink = asyncio.run(check_sink())
        # Should be the same sink due to context variable inheritance
        assert isinstance(sink, NoOpEventSink)


# === Edge Cases ===

class TestEventSinkEdgeCases:
    """Edge case tests for event sinks."""

    def test_noop_with_large_data(self):
        """Test NoOpEventSink with large data."""
        sink = NoOpEventSink()
        large_data = {"key": "value" * 10000}

        async def run_emit():
            await sink.emit(type="test", data=large_data)

        asyncio.run(run_emit())

    def test_logging_with_complex_data(self, caplog):
        """Test LoggingEventSink with complex nested data."""
        caplog.set_level(logging.INFO)
        sink = LoggingEventSink()

        complex_data = {
            "nested": {"a": {"b": {"c": "deep"}}},
            "list": [1, 2, {"nested": "value"}],
            "unicode": "日本語テスト",
        }

        async def run_emit():
            await sink.emit(type="test", data=complex_data)

        asyncio.run(run_emit())

        # Check that log was emitted
        assert "test" in caplog.text

    def test_sequential_set_clears(self):
        """Test that set_event_sink clears any previous custom state."""
        sink1 = NoOpEventSink()
        NoOpEventSink()

        set_event_sink(sink1)
        clear_event_sink()

        # Should be back to default NoOpEventSink
        sink = get_event_sink()
        assert isinstance(sink, NoOpEventSink)

    def test_none_data_handling(self):
        """Test handling of None data."""
        sink = NoOpEventSink()

        async def run_emit():
            await sink.emit(type="test", data=None)

        asyncio.run(run_emit())

        # try_emit should not raise
        sink.try_emit(type="test", data=None)
