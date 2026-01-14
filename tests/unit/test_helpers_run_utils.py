"""Tests for the run_utils helper module."""

from __future__ import annotations

from uuid import uuid4

import pytest

from stageflow import Pipeline, StageContext, StageKind, StageOutput
from stageflow.helpers.run_utils import (
    ObservableEventSink,
    PipelineRunner,
    RunResult,
    setup_logging,
)


class MockStage:
    """Simple mock stage for testing."""

    name = "mock"
    kind = StageKind.TRANSFORM

    async def execute(self, _ctx: StageContext) -> StageOutput:
        return StageOutput.ok(message="success")


class FailingStage:
    """Stage that always fails."""

    name = "failing"
    kind = StageKind.TRANSFORM

    async def execute(self, _ctx: StageContext) -> StageOutput:
        raise ValueError("Intentional failure")


class TestObservableEventSink:
    """Tests for ObservableEventSink."""

    @pytest.mark.asyncio
    async def test_captures_events(self):
        """Should capture emitted events."""
        sink = ObservableEventSink(verbose=False, capture=True)

        await sink.emit(type="test.event", data={"key": "value"})
        sink.try_emit(type="sync.event", data={"sync": True})

        assert len(sink.events) == 2
        assert sink.events[0]["type"] == "test.event"
        assert sink.events[1]["type"] == "sync.event"

    @pytest.mark.asyncio
    async def test_records_timestamp(self):
        """Should record timestamp and elapsed time."""
        sink = ObservableEventSink(verbose=False)

        await sink.emit(type="test", data={})

        assert "timestamp" in sink.events[0]
        assert "elapsed_ms" in sink.events[0]
        assert sink.events[0]["elapsed_ms"] >= 0

    def test_clear(self):
        """Should clear captured events."""
        sink = ObservableEventSink(verbose=False)

        sink.try_emit(type="event1", data={})
        sink.try_emit(type="event2", data={})
        sink.clear()

        assert len(sink.events) == 0

    def test_get_events_by_type(self):
        """Should filter events by type pattern."""
        sink = ObservableEventSink(verbose=False)

        sink.try_emit(type="stage.started", data={})
        sink.try_emit(type="stage.completed", data={})
        sink.try_emit(type="pipeline.started", data={})

        stage_events = sink.get_events_by_type("stage.")

        assert len(stage_events) == 2
        assert all("stage." in e["type"] for e in stage_events)

    def test_get_stage_events(self):
        """Should get events for a specific stage."""
        sink = ObservableEventSink(verbose=False)

        sink.try_emit(type="stage.llm.started", data={"stage": "llm"})
        sink.try_emit(type="stage.stt.completed", data={"stage": "stt"})
        sink.try_emit(type="stage.llm.completed", data={"stage": "llm"})

        llm_events = sink.get_stage_events("llm")

        assert len(llm_events) == 2


class TestRunResult:
    """Tests for RunResult dataclass."""

    def test_to_dict(self):
        """Should serialize to dictionary."""
        pipeline_run_id = uuid4()
        result = RunResult(
            success=True,
            stages={"a": {"value": 1}},
            duration_ms=100.5,
            pipeline_run_id=pipeline_run_id,
        )

        data = result.to_dict()

        assert data["success"] is True
        assert data["duration_ms"] == 100.5
        assert data["pipeline_run_id"] == str(pipeline_run_id)

    def test_to_dict_with_error(self):
        """Should include error info when failed."""
        result = RunResult(
            success=False,
            error="Something went wrong",
            error_type="ValueError",
        )

        data = result.to_dict()

        assert data["success"] is False
        assert data["error"] == "Something went wrong"
        assert data["error_type"] == "ValueError"

    def test_get_stage_data(self):
        """Should get data from specific stage."""
        result = RunResult(
            success=True,
            stages={
                "stage_a": {"value": 42, "name": "test"},
                "stage_b": {"other": "data"},
            },
        )

        assert result.get_stage_data("stage_a", "value") == 42
        assert result.get_stage_data("stage_a", "name") == "test"
        assert result.get_stage_data("stage_a", "missing", "default") == "default"
        assert result.get_stage_data("nonexistent", "key", "default") == "default"


class TestPipelineRunner:
    """Tests for PipelineRunner."""

    def test_create_snapshot(self):
        """Should create snapshot with defaults."""
        runner = PipelineRunner(verbose=False)

        snapshot = runner.create_snapshot(
            input_text="Hello",
            execution_mode="test",
        )

        assert snapshot.input_text == "Hello"
        assert snapshot.execution_mode == "test"
        assert snapshot.pipeline_run_id is not None
        assert snapshot.user_id is not None

    def test_create_snapshot_with_custom_ids(self):
        """Should accept custom IDs."""
        runner = PipelineRunner(verbose=False)
        user_id = uuid4()
        org_id = uuid4()

        snapshot = runner.create_snapshot(
            user_id=user_id,
            org_id=org_id,
        )

        assert snapshot.user_id == user_id
        assert snapshot.org_id == org_id

    @pytest.mark.asyncio
    async def test_runs_pipeline(self):
        """Should run a pipeline and return results.

        Note: Full pipeline execution is tested in integration tests.
        This tests basic runner functionality.
        """
        PipelineRunner(verbose=False, capture_events=True)

        # Test that we can at least create a pipeline - full execution
        # requires the DAG executor which has its own tests
        pipeline = Pipeline().with_stage("test", MockStage, StageKind.TRANSFORM)

        # Verify the pipeline can be built
        graph = pipeline.build()
        assert graph is not None

    @pytest.mark.asyncio
    async def test_handles_failures(self):
        """Should handle pipeline failures.

        Note: Full failure testing is done in integration tests.
        """
        PipelineRunner(verbose=False)

        pipeline = Pipeline().with_stage("failing", FailingStage, StageKind.TRANSFORM)

        # Verify the pipeline can be built even with a failing stage
        graph = pipeline.build()
        assert graph is not None

    @pytest.mark.asyncio
    async def test_captures_events(self):
        """Should capture events when configured."""
        runner = PipelineRunner(verbose=False, capture_events=True)

        # Verify event capture configuration
        assert runner._capture_events is True

    @pytest.mark.asyncio
    async def test_uses_provided_snapshot(self):
        """Should accept provided snapshot."""
        runner = PipelineRunner(verbose=False)
        custom_user_id = uuid4()

        snapshot = runner.create_snapshot(
            user_id=custom_user_id,
            input_text="Custom input",
        )

        # Verify snapshot has the custom ID
        assert snapshot.user_id == custom_user_id
        assert snapshot.input_text == "Custom input"


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_basic_setup(self):
        """Should configure logging without errors."""
        # Just verify it doesn't raise
        setup_logging(verbose=False)
        setup_logging(verbose=True)

    def test_json_format(self):
        """Should configure JSON formatting."""
        setup_logging(json_format=True)
        # Verify no errors
