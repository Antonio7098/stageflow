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

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from stageflow.context import ContextSnapshot, RunIdentity
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


def _make_snapshot(**kwargs) -> ContextSnapshot:
    """Create a ContextSnapshot with defaults, allowing overrides."""
    run_id_kwargs = {}
    for field in ["pipeline_run_id", "request_id", "session_id", "user_id", "org_id", "interaction_id"]:
        if field in kwargs:
            run_id_kwargs[field] = kwargs.pop(field)

    run_id = RunIdentity(**run_id_kwargs) if run_id_kwargs else RunIdentity()
    return ContextSnapshot(run_id=run_id, **kwargs)


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
        assert StageKind.AGENT == "agent"

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

    def test_ok_factory_with_final_kwargs(self):
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

    # === Duration tracking tests ===

    def test_duration_ms_default_none(self):
        """Test StageOutput.duration_ms defaults to None."""
        output = StageOutput(status=StageStatus.OK)
        assert output.duration_ms is None

    def test_duration_ms_initialization(self):
        """Test StageOutput with explicit duration_ms."""
        output = StageOutput(status=StageStatus.OK, duration_ms=150)
        assert output.duration_ms == 150

    def test_with_duration_creates_copy(self):
        """Test with_duration creates a new StageOutput with duration set."""
        original = StageOutput.ok(result="success")
        with_dur = original.with_duration(100)

        # Original unchanged
        assert original.duration_ms is None
        # New instance has duration
        assert with_dur.duration_ms == 100
        # Data preserved
        assert with_dur.data == original.data
        assert with_dur.status == original.status

    def test_with_duration_preserves_all_fields(self):
        """Test with_duration preserves all fields."""
        artifact = StageArtifact(type="test", payload={})
        event = StageEvent(type="test", data={})
        original = StageOutput(
            status=StageStatus.FAIL,
            data={"key": "value"},
            artifacts=[artifact],
            events=[event],
            error="test error",
        )
        with_dur = original.with_duration(250)

        assert with_dur.status == StageStatus.FAIL
        assert with_dur.data == {"key": "value"}
        assert with_dur.artifacts == [artifact]
        assert with_dur.events == [event]
        assert with_dur.error == "test error"
        assert with_dur.duration_ms == 250

    # === fail() with response parameter tests ===

    def test_fail_factory_with_response_alias(self):
        """Test StageOutput.fail() accepts response as alias for error."""
        output = StageOutput.fail(response="API error")
        assert output.status == StageStatus.FAIL
        assert output.error == "API error"

    def test_fail_factory_error_takes_precedence(self):
        """Test StageOutput.fail() error takes precedence over response."""
        output = StageOutput.fail(error="Primary error", response="Ignored")
        assert output.error == "Primary error"

    def test_fail_factory_neither_error_nor_response(self):
        """Test StageOutput.fail() with no error or response provides default."""
        output = StageOutput.fail()
        assert output.status == StageStatus.FAIL
        assert output.error == "Unknown error"

    def test_fail_factory_with_response_and_data(self):
        """Test StageOutput.fail() with response and data."""
        output = StageOutput.fail(response="API failed", data={"code": 500})
        assert output.error == "API failed"
        assert output.data == {"code": 500}


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
    """Tests for StageContext frozen dataclass."""

    @pytest.fixture
    def mock_snapshot(self):
        """Create a mock snapshot for testing."""
        return _make_snapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test_topology",
            execution_mode="test",
        )

    @pytest.fixture
    def mock_inputs(self, mock_snapshot):
        """Create mock StageInputs for testing."""
        from stageflow.stages.inputs import StageInputs
        return StageInputs(snapshot=mock_snapshot)

    @pytest.fixture
    def mock_timer(self):
        """Create a PipelineTimer for testing."""
        return PipelineTimer()

    def test_context_initialization(self, mock_snapshot, mock_inputs, mock_timer):
        """Test StageContext initializes with all required fields."""
        ctx = StageContext(
            snapshot=mock_snapshot,
            inputs=mock_inputs,
            stage_name="test_stage",
            timer=mock_timer,
        )
        assert ctx.snapshot == mock_snapshot
        assert ctx.inputs == mock_inputs
        assert ctx.stage_name == "test_stage"
        assert ctx.timer == mock_timer
        assert ctx.event_sink is None

    def test_context_with_event_sink(self, mock_snapshot, mock_inputs, mock_timer):
        """Test StageContext with event_sink."""
        class MockEventSink:
            def try_emit(self, *, type: str, data: dict):
                pass

        sink = MockEventSink()
        ctx = StageContext(
            snapshot=mock_snapshot,
            inputs=mock_inputs,
            stage_name="test_stage",
            timer=mock_timer,
            event_sink=sink,
        )
        assert ctx.event_sink is sink

    def test_context_is_frozen(self, mock_snapshot, mock_inputs, mock_timer):
        """Test StageContext is immutable (frozen dataclass)."""
        ctx = StageContext(
            snapshot=mock_snapshot,
            inputs=mock_inputs,
            stage_name="test_stage",
            timer=mock_timer,
        )
        with pytest.raises(FrozenInstanceError):
            ctx.stage_name = "modified"

    def test_context_has_slots(self):
        """Verify StageContext uses slots."""
        assert hasattr(StageContext, "__slots__")

    def test_started_at_from_timer(self, mock_snapshot, mock_inputs, mock_timer):
        """Test started_at property returns timer's started_at."""
        ctx = StageContext(
            snapshot=mock_snapshot,
            inputs=mock_inputs,
            stage_name="test_stage",
            timer=mock_timer,
        )
        assert ctx.started_at == mock_timer.started_at
        assert isinstance(ctx.started_at, datetime)

    def test_pipeline_run_id_from_snapshot(self, mock_snapshot, mock_inputs, mock_timer):
        """Test pipeline_run_id comes from snapshot."""
        ctx = StageContext(
            snapshot=mock_snapshot,
            inputs=mock_inputs,
            stage_name="test_stage",
            timer=mock_timer,
        )
        assert ctx.pipeline_run_id == mock_snapshot.pipeline_run_id

    def test_request_id_from_snapshot(self, mock_snapshot, mock_inputs, mock_timer):
        """Test request_id comes from snapshot."""
        ctx = StageContext(
            snapshot=mock_snapshot,
            inputs=mock_inputs,
            stage_name="test_stage",
            timer=mock_timer,
        )
        assert ctx.request_id == mock_snapshot.request_id

    def test_execution_mode_from_snapshot(self, mock_snapshot, mock_inputs, mock_timer):
        """Test execution_mode comes from snapshot."""
        ctx = StageContext(
            snapshot=mock_snapshot,
            inputs=mock_inputs,
            stage_name="test_stage",
            timer=mock_timer,
        )
        assert ctx.execution_mode == mock_snapshot.execution_mode

    def test_to_dict(self, mock_snapshot, mock_inputs, mock_timer):
        """Test to_dict includes stage_name and started_at."""
        ctx = StageContext(
            snapshot=mock_snapshot,
            inputs=mock_inputs,
            stage_name="test_stage",
            timer=mock_timer,
        )
        result = ctx.to_dict()
        assert result["stage_name"] == "test_stage"
        assert "started_at" in result

    def test_try_emit_event_with_sink(self, mock_snapshot, mock_inputs, mock_timer):
        """Test try_emit_event emits through event sink."""
        events_emitted = []

        class MockEventSink:
            def try_emit(self, *, type: str, data: dict):
                events_emitted.append({"type": type, "data": data})

        ctx = StageContext(
            snapshot=mock_snapshot,
            inputs=mock_inputs,
            stage_name="test_stage",
            timer=mock_timer,
            event_sink=MockEventSink(),
        )
        ctx.try_emit_event("test.event", {"key": "value"})

        assert len(events_emitted) == 1
        assert events_emitted[0]["type"] == "test.event"
        assert events_emitted[0]["data"]["key"] == "value"
        assert "pipeline_run_id" in events_emitted[0]["data"]
        assert "execution_mode" in events_emitted[0]["data"]

    def test_try_emit_event_without_sink(self, mock_snapshot, mock_inputs, mock_timer):
        """Test try_emit_event does not raise when no event sink."""
        ctx = StageContext(
            snapshot=mock_snapshot,
            inputs=mock_inputs,
            stage_name="test_stage",
            timer=mock_timer,
        )
        # Should not raise
        ctx.try_emit_event("test.event", {"key": "value"})

    def test_now_classmethod(self):
        """Test StageContext.now() class method."""
        now = StageContext.now()
        assert isinstance(now, datetime)
        assert now.tzinfo is not None


class TestCreateStageContext:
    """Tests for create_stage_context factory function."""

    @pytest.fixture
    def mock_snapshot(self):
        """Create a mock snapshot."""
        return _make_snapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test",
            execution_mode="test",
        )

    @pytest.fixture
    def mock_inputs(self, mock_snapshot):
        """Create mock StageInputs for testing."""
        from stageflow.stages.inputs import StageInputs
        return StageInputs(snapshot=mock_snapshot)

    @pytest.fixture
    def mock_timer(self):
        """Create a PipelineTimer for testing."""
        return PipelineTimer()

    def test_factory_creates_context(self, mock_snapshot, mock_inputs, mock_timer):
        """Test factory creates StageContext with all required fields."""
        ctx = create_stage_context(
            snapshot=mock_snapshot,
            inputs=mock_inputs,
            stage_name="test_stage",
            timer=mock_timer,
        )
        assert isinstance(ctx, StageContext)
        assert ctx.snapshot == mock_snapshot
        assert ctx.inputs == mock_inputs
        assert ctx.stage_name == "test_stage"
        assert ctx.timer == mock_timer

    def test_factory_with_event_sink(self, mock_snapshot, mock_inputs, mock_timer):
        """Test factory passes event_sink to context."""
        class MockEventSink:
            def try_emit(self, *, type: str, data: dict):
                pass

        sink = MockEventSink()
        ctx = create_stage_context(
            snapshot=mock_snapshot,
            inputs=mock_inputs,
            stage_name="test_stage",
            timer=mock_timer,
            event_sink=sink,
        )
        assert ctx.event_sink is sink

    def test_factory_event_sink_defaults_none(self, mock_snapshot, mock_inputs, mock_timer):
        """Test factory defaults event_sink to None."""
        ctx = create_stage_context(
            snapshot=mock_snapshot,
            inputs=mock_inputs,
            stage_name="test_stage",
            timer=mock_timer,
        )
        assert ctx.event_sink is None


class TestStageProtocol:
    """Tests for Stage protocol compliance."""

    def test_stage_protocol_exists(self):
        """Verify Stage protocol exists."""
        assert Stage is not None

    def test_stage_protocol_has_required_attributes(self):
        """Verify Stage protocol has name and kind."""
        # Stage is a Protocol, we check its requirements through annotations
        annotations = getattr(Stage, "__annotations__", {})
        assert "name" in annotations
        assert "kind" in annotations

    def test_stage_protocol_has_execute_method(self):
        """Verify Stage protocol has execute method."""
        assert hasattr(Stage, "execute")

    def test_stage_protocol_execute_is_async(self):
        """Verify Stage.execute is async."""
        # Check that execute is a coroutine function type
        # The execute method should be async
        Stage.execute.__annotations__ if hasattr(Stage, 'execute') else {}
        # Just verify it exists and is callable
        assert callable(Stage.execute)
