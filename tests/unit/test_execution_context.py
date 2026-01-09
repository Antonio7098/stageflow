"""Tests for ExecutionContext protocol and implementations."""

from uuid import uuid4

import pytest

from stageflow.context import ContextSnapshot
from stageflow.core import StageContext
from stageflow.protocols import ExecutionContext
from stageflow.stages.context import PipelineContext
from stageflow.tools.adapters import DictContextAdapter, adapt_context


class TestExecutionContextProtocol:
    """Test that ExecutionContext protocol is properly defined."""

    def test_stage_context_implements_protocol(self):
        """StageContext should implement ExecutionContext protocol."""
        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test_topology",
            execution_mode="practice",
        )
        ctx = StageContext(snapshot=snapshot)

        # Check protocol attributes exist
        assert hasattr(ctx, 'pipeline_run_id')
        assert hasattr(ctx, 'request_id')
        assert hasattr(ctx, 'execution_mode')
        assert hasattr(ctx, 'to_dict')
        assert hasattr(ctx, 'try_emit_event')

        # Check isinstance works with runtime_checkable
        assert isinstance(ctx, ExecutionContext)

    def test_pipeline_context_implements_protocol(self):
        """PipelineContext should implement ExecutionContext protocol."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            execution_mode="practice",
        )

        # Check protocol attributes exist
        assert hasattr(ctx, 'pipeline_run_id')
        assert hasattr(ctx, 'request_id')
        assert hasattr(ctx, 'execution_mode')
        assert hasattr(ctx, 'to_dict')
        assert hasattr(ctx, 'try_emit_event')

        # Check isinstance works with runtime_checkable
        assert isinstance(ctx, ExecutionContext)

    def test_dict_context_adapter_implements_protocol(self):
        """DictContextAdapter should implement ExecutionContext protocol."""
        ctx = DictContextAdapter({
            "pipeline_run_id": str(uuid4()),
            "request_id": str(uuid4()),
            "execution_mode": "practice",
        })

        # Check protocol attributes exist
        assert hasattr(ctx, 'pipeline_run_id')
        assert hasattr(ctx, 'request_id')
        assert hasattr(ctx, 'execution_mode')
        assert hasattr(ctx, 'to_dict')
        assert hasattr(ctx, 'try_emit_event')

        # Check isinstance works with runtime_checkable
        assert isinstance(ctx, ExecutionContext)


class TestStageContextExecutionContext:
    """Test StageContext ExecutionContext implementation."""

    def test_pipeline_run_id_from_snapshot(self):
        """pipeline_run_id should come from snapshot."""
        run_id = uuid4()
        snapshot = ContextSnapshot(
            pipeline_run_id=run_id,
            request_id=None,
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
            topology=None,
            execution_mode=None,
        )
        ctx = StageContext(snapshot=snapshot)
        assert ctx.pipeline_run_id == run_id

    def test_request_id_from_snapshot(self):
        """request_id should come from snapshot."""
        req_id = uuid4()
        snapshot = ContextSnapshot(
            pipeline_run_id=None,
            request_id=req_id,
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
            topology=None,
            execution_mode=None,
        )
        ctx = StageContext(snapshot=snapshot)
        assert ctx.request_id == req_id

    def test_execution_mode_from_snapshot(self):
        """execution_mode should come from snapshot."""
        snapshot = ContextSnapshot(
            pipeline_run_id=None,
            request_id=None,
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
            topology=None,
            execution_mode="doc_edit",
        )
        ctx = StageContext(snapshot=snapshot)
        assert ctx.execution_mode == "doc_edit"

    def test_to_dict_includes_snapshot_data(self):
        """to_dict should include snapshot data."""
        run_id = uuid4()
        snapshot = ContextSnapshot(
            pipeline_run_id=run_id,
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="chat_fast",
            execution_mode="practice",
        )
        ctx = StageContext(snapshot=snapshot)

        result = ctx.to_dict()

        assert result["pipeline_run_id"] == str(run_id)
        assert result["execution_mode"] == "practice"
        assert result["topology"] == "chat_fast"
        assert "started_at" in result

    def test_try_emit_event_with_event_sink(self):
        """try_emit_event should emit through event sink when available."""
        events_emitted = []

        class MockEventSink:
            def try_emit(self, *, type: str, data: dict):
                events_emitted.append({"type": type, "data": data})

            async def emit(self, *, type: str, data: dict):
                events_emitted.append({"type": type, "data": data})

        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
            topology=None,
            execution_mode="practice",
        )
        ctx = StageContext(
            snapshot=snapshot,
            config={"event_sink": MockEventSink()},
        )

        ctx.try_emit_event("test.event", {"key": "value"})

        assert len(events_emitted) == 1
        assert events_emitted[0]["type"] == "test.event"
        assert events_emitted[0]["data"]["key"] == "value"
        assert events_emitted[0]["data"]["execution_mode"] == "practice"

    def test_try_emit_event_without_event_sink(self):
        """try_emit_event should not raise when no event sink."""
        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
            topology=None,
            execution_mode=None,
        )
        ctx = StageContext(snapshot=snapshot)

        # Should not raise
        ctx.try_emit_event("test.event", {"key": "value"})


class TestPipelineContextExecutionContext:
    """Test PipelineContext ExecutionContext implementation."""

    def test_try_emit_event(self):
        """try_emit_event should emit through event sink."""
        events_emitted = []

        class MockEventSink:
            def try_emit(self, *, type: str, data: dict):
                events_emitted.append({"type": type, "data": data})

            async def emit(self, *, type: str, data: dict):
                events_emitted.append({"type": type, "data": data})

        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
            execution_mode="practice",
            topology="chat_fast",
            event_sink=MockEventSink(),
        )

        ctx.try_emit_event("test.event", {"key": "value"})

        assert len(events_emitted) == 1
        assert events_emitted[0]["type"] == "test.event"
        assert events_emitted[0]["data"]["key"] == "value"
        assert events_emitted[0]["data"]["execution_mode"] == "practice"
        assert events_emitted[0]["data"]["topology"] == "chat_fast"


class TestDictContextAdapter:
    """Test DictContextAdapter."""

    def test_pipeline_run_id_from_string(self):
        """Should parse UUID from string."""
        run_id = uuid4()
        adapter = DictContextAdapter({"pipeline_run_id": str(run_id)})
        assert adapter.pipeline_run_id == run_id

    def test_pipeline_run_id_from_uuid(self):
        """Should accept UUID directly."""
        run_id = uuid4()
        adapter = DictContextAdapter({"pipeline_run_id": run_id})
        assert adapter.pipeline_run_id == run_id

    def test_pipeline_run_id_none(self):
        """Should return None when not present."""
        adapter = DictContextAdapter({})
        assert adapter.pipeline_run_id is None

    def test_pipeline_run_id_invalid(self):
        """Should return None for invalid UUID."""
        adapter = DictContextAdapter({"pipeline_run_id": "not-a-uuid"})
        assert adapter.pipeline_run_id is None

    def test_request_id_from_string(self):
        """Should parse UUID from string."""
        req_id = uuid4()
        adapter = DictContextAdapter({"request_id": str(req_id)})
        assert adapter.request_id == req_id

    def test_execution_mode(self):
        """Should return execution_mode."""
        adapter = DictContextAdapter({"execution_mode": "practice"})
        assert adapter.execution_mode == "practice"

    def test_to_dict(self):
        """Should return copy of data."""
        data = {"key": "value", "execution_mode": "practice"}
        adapter = DictContextAdapter(data)
        result = adapter.to_dict()

        assert result == data
        assert result is not data  # Should be a copy

    def test_try_emit_event(self):
        """Should not raise when emitting events."""
        adapter = DictContextAdapter({"execution_mode": "practice"})
        # Should not raise
        adapter.try_emit_event("test.event", {"key": "value"})


class TestAdaptContext:
    """Test adapt_context function."""

    def test_adapt_stage_context(self):
        """Should return StageContext unchanged."""
        snapshot = ContextSnapshot(
            pipeline_run_id=uuid4(),
            request_id=None,
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
            topology=None,
            execution_mode=None,
        )
        ctx = StageContext(snapshot=snapshot)

        result = adapt_context(ctx)
        assert result is ctx

    def test_adapt_pipeline_context(self):
        """Should return PipelineContext unchanged."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=None,
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
        )

        result = adapt_context(ctx)
        assert result is ctx

    def test_adapt_dict(self):
        """Should wrap dict in DictContextAdapter."""
        data = {"pipeline_run_id": str(uuid4()), "execution_mode": "practice"}

        result = adapt_context(data)

        assert isinstance(result, DictContextAdapter)
        assert result.execution_mode == "practice"

    def test_adapt_unsupported_type(self):
        """Should raise TypeError for unsupported types."""
        with pytest.raises(TypeError, match="Unsupported context type"):
            adapt_context("not a context")

    def test_adapt_dict_context_adapter(self):
        """Should return DictContextAdapter unchanged."""
        adapter = DictContextAdapter({"execution_mode": "practice"})

        result = adapt_context(adapter)
        assert result is adapter
