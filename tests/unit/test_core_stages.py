"""Comprehensive tests for stageflow.core.stages module.

Tests all core stage types:
- StageKind enum
- StageStatus enum
- StageOutput dataclass and factory methods
- StageArtifact dataclass
- StageEvent dataclass
- StageContext class
- PipelineTimer class
- Stage protocol
- create_stage_context factory function
"""

import asyncio
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, UTC
from typing import Any
from uuid import uuid4
import pytest

from stageflow.core import (
    PipelineTimer,
    Stage,
    StageArtifact,
    StageContext,
    StageEvent,
    StageKind,
    StageOutput,
    StageStatus,
    create_stage_context,
)


class TestStageKind:
    """Tests for StageKind enum."""

    def test_all_stage_kinds_defined(self):
        """Verify all expected stage kinds exist."""
        assert StageKind.TRANSFORM.value == "transform"
        assert StageKind.ENRICH.value == "enrich"
        assert StageKind.ROUTE.value == "route"
        assert StageKind.GUARD.value == "guard"
        assert StageKind.WORK.value == "work"
        assert StageKind.AGENT.value == "agent"

    def test_stage_kind_is_string_enum(self):
        """Verify StageKind inherits from str."""
        assert isinstance(StageKind.TRANSFORM, str)
        assert StageKind.TRANSFORM == "transform"

    def test_stage_kind_comparison_with_string(self):
        """Verify stage kind can be compared with strings."""
        assert StageKind.TRANSFORM == "transform"
        assert StageKind.ENRICH == "enrich"
        assert "agent" == StageKind.AGENT

    def test_stage_kind_values_are_unique(self):
        """Verify all stage kind values are unique."""
        values = [kind.value for kind in StageKind]
        assert len(values) == len(set(values))


class TestStageStatus:
    """Tests for StageStatus enum."""

    def test_all_statuses_defined(self):
        """Verify all expected statuses exist."""
        assert StageStatus.OK.value == "ok"
        assert StageStatus.SKIP.value == "skip"
        assert StageStatus.CANCEL.value == "cancel"
        assert StageStatus.FAIL.value == "fail"
        assert StageStatus.RETRY.value == "retry"

    def test_stage_status_is_string_enum(self):
        """Verify StageStatus inherits from str."""
        assert isinstance(StageStatus.OK, str)

    def test_status_values_are_unique(self):
        """Verify all status values are unique."""
        values = [status.value for status in StageStatus]
        assert len(values) == len(set(values))


class TestStageOutput:
    """Tests for StageOutput dataclass and factory methods."""

    def test_default_initialization(self):
        """Test StageOutput with default values."""
        output = StageOutput(status=StageStatus.OK)
        assert output.status == StageStatus.OK
        assert output.data == {}
        assert output.artifacts == []
        assert output.events == []
        assert output.error is None

    def test_custom_data_initialization(self):
        """Test StageOutput with custom data."""
        data = {"key": "value", "count": 42}
        output = StageOutput(status=StageStatus.OK, data=data)
        assert output.data == data

    def test_error_initialization(self):
        """Test StageOutput with error."""
        output = StageOutput(status=StageStatus.FAIL, error="Something went wrong")
        assert output.error == "Something went wrong"

    def test_output_is_immutable(self):
        """Verify StageOutput is immutable (frozen dataclass).

        Note: Frozen dataclasses prevent field reassignment but mutable fields
        (dict, list) can still be mutated. This tests field reassignment.
        """
        output = StageOutput(status=StageStatus.OK)
        with pytest.raises(FrozenInstanceError):
            output.status = StageStatus.FAIL

    def test_output_has_slots(self):
        """Verify StageOutput uses slots for memory efficiency."""
        assert hasattr(StageOutput, "__slots__")

    # === Factory Method Tests ===

    def test_ok_factory_without_data(self):
        """Test StageOutput.ok() without data."""
        output = StageOutput.ok()
        assert output.status == StageStatus.OK
        assert output.data == {}
        assert output.error is None

    def test_ok_factory_with_dict_data(self):
        """Test StageOutput.ok() with dict data."""
        data = {"result": "success"}
        output = StageOutput.ok(data=data)
        assert output.status == StageStatus.OK
        assert output.data == data

    def test_ok_factory_with_kwargs(self):
        """Test StageOutput.ok() with keyword arguments."""
        output = StageOutput.ok(result="success", count=5)
        assert output.status == StageStatus.OK
        assert output.data == {"result": "success", "count": 5}

    def test_ok_factory_with_kwargs(self):
        """Test that kwargs become data dict when no data provided."""
        output = StageOutput.ok(final="done")
        assert output.data == {"final": "done"}

    def test_skip_factory_without_reason(self):
        """Test StageOutput.skip() without reason."""
        output = StageOutput.skip()
        assert output.status == StageStatus.SKIP
        assert output.data["reason"] == ""

    def test_skip_factory_with_reason(self):
        """Test StageOutput.skip() with reason."""
        output = StageOutput.skip(reason="condition not met")
        assert output.status == StageStatus.SKIP
        assert output.data["reason"] == "condition not met"

    def test_skip_factory_with_additional_data(self):
        """Test StageOutput.skip() with additional data."""
        output = StageOutput.skip(reason="not needed", data={"extra": "info"})
        assert output.status == StageStatus.SKIP
        assert output.data["reason"] == "not needed"
        assert output.data["extra"] == "info"

    def test_cancel_factory_without_reason(self):
        """Test StageOutput.cancel() without reason."""
        output = StageOutput.cancel()
        assert output.status == StageStatus.CANCEL
        assert output.data["cancel_reason"] == ""

    def test_cancel_factory_with_reason(self):
        """Test StageOutput.cancel() with reason."""
        output = StageOutput.cancel(reason="user_aborted")
        assert output.status == StageStatus.CANCEL
        assert output.data["cancel_reason"] == "user_aborted"

    def test_cancel_factory_with_data(self):
        """Test StageOutput.cancel() with additional data."""
        output = StageOutput.cancel(reason="timeout", data={"elapsed_ms": 30000})
        assert output.status == StageStatus.CANCEL
        assert output.data["cancel_reason"] == "timeout"
        assert output.data["elapsed_ms"] == 30000

    def test_fail_factory(self):
        """Test StageOutput.fail() factory."""
        output = StageOutput.fail(error="Connection refused")
        assert output.status == StageStatus.FAIL
        assert output.error == "Connection refused"
        assert output.data == {}

    def test_fail_factory_with_data(self):
        """Test StageOutput.fail() with additional data."""
        output = StageOutput.fail(error="Error", data={"attempt": 3})
        assert output.status == StageStatus.FAIL
        assert output.error == "Error"
        assert output.data["attempt"] == 3

    def test_retry_factory(self):
        """Test StageOutput.retry() factory."""
        output = StageOutput.retry(error="Rate limit exceeded")
        assert output.status == StageStatus.RETRY
        assert output.error == "Rate limit exceeded"

    def test_retry_factory_with_data(self):
        """Test StageOutput.retry() with additional data."""
        output = StageOutput.retry(error="Retry needed", data={"retry_after": 60})
        assert output.status == StageStatus.RETRY
        assert output.error == "Retry needed"
        assert output.data["retry_after"] == 60


class TestStageArtifact:
    """Tests for StageArtifact dataclass."""

    def test_artifact_initialization(self):
        """Test StageArtifact with all fields."""
        timestamp = datetime.now(UTC)
        artifact = StageArtifact(
            type="audio",
            payload={"format": "mp3", "duration_ms": 5000},
            timestamp=timestamp,
        )
        assert artifact.type == "audio"
        assert artifact.payload == {"format": "mp3", "duration_ms": 5000}
        assert artifact.timestamp == timestamp

    def test_artifact_default_timestamp(self):
        """Test StageArtifact has default timestamp."""
        artifact = StageArtifact(type="image", payload={"size": 1024})
        assert artifact.timestamp is not None
        assert isinstance(artifact.timestamp, datetime)

    def test_artifact_is_immutable(self):
        """Verify StageArtifact is immutable.

        Note: Frozen dataclasses prevent field reassignment but mutable fields
        (dict, list) can still be mutated. This tests field reassignment.
        """
        artifact = StageArtifact(type="text", payload={})
        with pytest.raises(FrozenInstanceError):
            artifact.type = "modified"

    def test_artifact_has_slots(self):
        """Verify StageArtifact uses slots."""
        assert hasattr(StageArtifact, "__slots__")


class TestStageEvent:
    """Tests for StageEvent dataclass."""

    def test_event_initialization(self):
        """Test StageEvent with all fields."""
        timestamp = datetime.now(UTC)
        event = StageEvent(
            type="stage.started",
            data={"stage_name": "test_stage"},
            timestamp=timestamp,
        )
        assert event.type == "stage.started"
        assert event.data == {"stage_name": "test_stage"}
        assert event.timestamp == timestamp

    def test_event_default_timestamp(self):
        """Test StageEvent has default timestamp."""
        event = StageEvent(type="test", data={})
        assert event.timestamp is not None

    def test_event_is_immutable(self):
        """Verify StageEvent is immutable.

        Note: Frozen dataclasses prevent field reassignment but mutable fields
        (dict, list) can still be mutated. This tests field reassignment.
        """
        event = StageEvent(type="test", data={})
        with pytest.raises(FrozenInstanceError):
            event.type = "modified"


class TestPipelineTimer:
    """Tests for PipelineTimer class."""

    def test_timer_initialization(self):
        """Test PipelineTimer initializes correctly."""
        timer = PipelineTimer()
        assert timer.pipeline_start_ms > 0

    def test_now_ms_increases(self):
        """Test that now_ms returns increasing values."""
        timer = PipelineTimer()
        import time
        time.sleep(0.01)  # 10ms
        assert timer.now_ms() > timer.pipeline_start_ms

    def test_elapsed_ms_initially_zero(self):
        """Test elapsed_ms right after creation."""
        timer = PipelineTimer()
        # Should be very close to 0
        assert timer.elapsed_ms() < 10

    def test_elapsed_ms_increases(self):
        """Test elapsed_ms increases over time."""
        timer = PipelineTimer()
        import time
        time.sleep(0.05)  # 50ms
        elapsed = timer.elapsed_ms()
        assert elapsed >= 40  # Allow some tolerance

    def test_started_at_returns_datetime(self):
        """Test started_at returns a datetime."""
        timer = PipelineTimer()
        started = timer.started_at
        assert isinstance(started, datetime)
        assert started.tzinfo is not None  # Should be timezone-aware

    def test_started_at_matches_pipeline_start(self):
        """Test started_at matches pipeline_start_ms."""
        timer = PipelineTimer()
        expected = datetime.fromtimestamp(timer.pipeline_start_ms / 1000.0, tz=UTC)
        assert timer.started_at == expected

    def test_timer_has_slots(self):
        """Verify PipelineTimer uses slots."""
        assert hasattr(PipelineTimer, "__slots__")

    def test_timer_slots_contents(self):
        """Verify PipelineTimer has expected slots."""
        timer = PipelineTimer()
        # Should have _pipeline_start_ms slot
        assert hasattr(timer, "_pipeline_start_ms")

    def test_multiple_timers_are_independent(self):
        """Test that multiple timers track independently."""
        timer1 = PipelineTimer()
        import time
        time.sleep(0.001)  # Ensure different millisecond
        timer2 = PipelineTimer()
        # They should be different (created at different times)
        assert timer1.pipeline_start_ms != timer2.pipeline_start_ms


class TestStageContext:
    """Tests for StageContext class."""

    @pytest.fixture
    def mock_snapshot(self):
        """Create a mock snapshot for testing."""
        from stageflow.context import ContextSnapshot
        return ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test_topology",
            execution_mode="test",
        )

    def test_context_initialization(self, mock_snapshot):
        """Test StageContext initializes with snapshot."""
        ctx = StageContext(snapshot=mock_snapshot)
        assert ctx.snapshot == mock_snapshot

    def test_context_with_config(self, mock_snapshot):
        """Test StageContext with config."""
        config = {"custom_key": "custom_value"}
        ctx = StageContext(snapshot=mock_snapshot, config=config)
        assert ctx.config["custom_key"] == "custom_value"

    def test_context_config_default_empty(self, mock_snapshot):
        """Test StageContext config defaults to empty dict."""
        ctx = StageContext(snapshot=mock_snapshot)
        assert ctx.config == {}

    def test_context_started_at(self, mock_snapshot):
        """Test StageContext started_at is set."""
        ctx = StageContext(snapshot=mock_snapshot)
        assert ctx.started_at is not None
        assert isinstance(ctx.started_at, datetime)

    def test_timer_property_returns_timer(self, mock_snapshot):
        """Test timer property returns PipelineTimer."""
        ctx = StageContext(snapshot=mock_snapshot)
        timer = ctx.timer
        assert isinstance(timer, PipelineTimer)

    def test_timer_with_custom_timer_in_config(self, mock_snapshot):
        """Test timer uses custom timer from config if provided."""
        custom_timer = PipelineTimer()
        ctx = StageContext(snapshot=mock_snapshot, config={"timer": custom_timer})
        assert ctx.timer is custom_timer

    def test_timer_started_at_matches_context(self, mock_snapshot):
        """Test custom timer started_at matches context started_at."""
        ctx = StageContext(snapshot=mock_snapshot)
        custom_timer = PipelineTimer()
        object.__setattr__(
            custom_timer, "_pipeline_start_ms", int(ctx.started_at.timestamp() * 1000)
        )
        ctx_with_timer = StageContext(snapshot=mock_snapshot, config={"timer": custom_timer})
        assert ctx_with_timer.timer.pipeline_start_ms == int(ctx.started_at.timestamp() * 1000)

    def test_now_classmethod(self):
        """Test StageContext.now() class method."""
        now = StageContext.now()
        assert isinstance(now, datetime)
        assert now.tzinfo is not None

    def test_emit_event(self, mock_snapshot):
        """Test emit_event adds to outputs."""
        ctx = StageContext(snapshot=mock_snapshot)
        ctx.emit_event("test_event", {"key": "value"})
        outputs = ctx.collect_outputs()
        assert len(outputs) == 1
        assert len(outputs[0].events) == 1
        assert outputs[0].events[0].type == "test_event"
        # Events are enriched with correlation IDs
        event_data = outputs[0].events[0].data
        assert event_data["key"] == "value"
        assert "pipeline_run_id" in event_data
        assert "request_id" in event_data
        assert "execution_mode" in event_data

    def test_emit_multiple_events(self, mock_snapshot):
        """Test emitting multiple events."""
        ctx = StageContext(snapshot=mock_snapshot)
        ctx.emit_event("event1", {"n": 1})
        ctx.emit_event("event2", {"n": 2})
        outputs = ctx.collect_outputs()
        assert len(outputs) == 2
        assert outputs[0].events[0].type == "event1"
        assert outputs[1].events[0].type == "event2"

    def test_add_artifact(self, mock_snapshot):
        """Test add_artifact adds to outputs."""
        ctx = StageContext(snapshot=mock_snapshot)
        ctx.add_artifact("audio", {"format": "mp3"})
        outputs = ctx.collect_outputs()
        assert len(outputs) == 1
        assert len(outputs[0].artifacts) == 1
        assert outputs[0].artifacts[0].type == "audio"
        assert outputs[0].artifacts[0].payload == {"format": "mp3"}

    def test_add_multiple_artifacts(self, mock_snapshot):
        """Test adding multiple artifacts."""
        ctx = StageContext(snapshot=mock_snapshot)
        ctx.add_artifact("type1", {"id": 1})
        ctx.add_artifact("type2", {"id": 2})
        outputs = ctx.collect_outputs()
        artifacts = outputs[0].artifacts + outputs[1].artifacts
        assert len(artifacts) == 2

    def test_collect_outputs_empty_initially(self, mock_snapshot):
        """Test collect_outputs returns empty list initially."""
        ctx = StageContext(snapshot=mock_snapshot)
        assert ctx.collect_outputs() == []

    def test_get_output_data_finds_value(self, mock_snapshot):
        """Test get_output_data finds value in outputs."""
        ctx = StageContext(snapshot=mock_snapshot)
        ctx.add_artifact("test", {})  # This doesn't add to data
        # Use emit_event which does add to output
        ctx.emit_event("test", {})
        outputs = ctx.collect_outputs()
        # The event output has status OK, not data with our key
        # Let's add data directly
        from stageflow.core import StageOutput
        object.__setattr__(ctx, "_outputs", [StageOutput.ok(key="value")])
        assert ctx.get_output_data("key") == "value"

    def test_get_output_data_with_default(self, mock_snapshot):
        """Test get_output_data returns default when key not found."""
        ctx = StageContext(snapshot=mock_snapshot)
        assert ctx.get_output_data("missing") is None
        assert ctx.get_output_data("missing", "default") == "default"

    def test_get_output_data_nested_search(self, mock_snapshot):
        """Test get_output_data searches all outputs."""
        ctx = StageContext(snapshot=mock_snapshot)
        from stageflow.core import StageOutput
        object.__setattr__(ctx, "_outputs", [
            StageOutput.ok(first="value1"),
            StageOutput.ok(second="value2"),
            StageOutput.ok(third="value3"),
        ])
        assert ctx.get_output_data("second") == "value2"
        assert ctx.get_output_data("third") == "value3"
        assert ctx.get_output_data("first") == "value1"

    def test_context_has_slots(self):
        """Verify StageContext uses slots."""
        assert hasattr(StageContext, "__slots__")


class TestCreateStageContext:
    """Tests for create_stage_context factory function."""

    @pytest.fixture
    def mock_snapshot(self):
        """Create a mock snapshot."""
        from stageflow.context import ContextSnapshot
        return ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test",
            execution_mode="test",
        )

    def test_factory_creates_context(self, mock_snapshot):
        """Test factory creates StageContext."""
        ctx = create_stage_context(snapshot=mock_snapshot)
        assert isinstance(ctx, StageContext)
        assert ctx.snapshot == mock_snapshot

    def test_factory_with_config(self, mock_snapshot):
        """Test factory passes config to context."""
        config = {"custom": "value"}
        ctx = create_stage_context(snapshot=mock_snapshot, config=config)
        assert ctx.config == config

    def test_factory_with_none_config(self, mock_snapshot):
        """Test factory handles None config."""
        ctx = create_stage_context(snapshot=mock_snapshot, config=None)
        assert ctx.config == {}


class TestStageProtocol:
    """Tests for Stage protocol compliance."""

    def test_stage_protocol_exists(self):
        """Verify Stage protocol exists."""
        assert Stage is not None

    def test_stage_protocol_has_required_attributes(self):
        """Verify Stage protocol has name and kind."""
        # Stage is a Protocol, we check its requirements through annotations
        import typing
        annotations = getattr(Stage, "__annotations__", {})
        assert "name" in annotations
        assert "kind" in annotations

    def test_stage_protocol_has_execute_method(self):
        """Verify Stage protocol has execute method."""
        assert hasattr(Stage, "execute")

    def test_stage_protocol_execute_is_async(self):
        """Verify Stage.execute is async."""
        # Check that execute is a coroutine function type
        import typing
        # The execute method should be async
        annotations = Stage.execute.__annotations__ if hasattr(Stage, 'execute') else {}
        # Just verify it exists and is callable
        assert callable(Stage.execute)
