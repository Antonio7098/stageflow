"""Comprehensive tests for stageflow.stages.context module.

Tests:
- PipelineContext class
- extract_quality_mode function
- extract_service function
"""

from datetime import datetime, UTC
from typing import Any
from uuid import uuid4
import pytest

from stageflow.events import NoOpEventSink
from stageflow.stages.context import (
    extract_quality_mode,
    extract_service,
    PipelineContext,
)


# === Test extract_service ===

class TestExtractService:
    """Tests for extract_service function."""

    def test_none_topology(self):
        """Test with None topology."""
        assert extract_service(None) is None

    def test_chat_fast(self):
        """Test chat_fast topology."""
        assert extract_service("chat_fast") == "chat"

    def test_voice_accurate(self):
        """Test voice_accurate topology."""
        assert extract_service("voice_accurate") == "voice"

    def test_fast_kernel(self):
        """Test kernel topology returns None."""
        assert extract_service("fast_kernel") is None

    def test_accurate_kernel(self):
        """Test accurate kernel returns None."""
        assert extract_service("accurate_kernel") is None

    def test_simple_service_name(self):
        """Test simple service name without mode."""
        assert extract_service("chat") == "chat"

    def test_underscore_in_service(self):
        """Test service with underscore."""
        # extract_service returns everything before the last underscore
        assert extract_service("web_chat_fast") == "web_chat"

    def test_practice_mode(self):
        """Test practice mode."""
        assert extract_service("voice_practice") == "voice"

    def test_balanced_mode(self):
        """Test balanced mode."""
        assert extract_service("chat_balanced") == "chat"

    def test_empty_string(self):
        """Test empty string."""
        assert extract_service("") == ""


# === Test extract_quality_mode ===

class TestExtractQualityMode:
    """Tests for extract_quality_mode function."""

    def test_none_topology(self):
        """Test with None topology."""
        assert extract_quality_mode(None) is None

    def test_chat_fast(self):
        """Test chat_fast topology."""
        assert extract_quality_mode("chat_fast") == "fast"

    def test_voice_accurate(self):
        """Test voice_accurate topology."""
        assert extract_quality_mode("voice_accurate") == "accurate"

    def test_fast_kernel(self):
        """Test kernel topology extracts prefix."""
        assert extract_quality_mode("fast_kernel") == "fast"

    def test_accurate_kernel(self):
        """Test accurate kernel."""
        assert extract_quality_mode("accurate_kernel") == "accurate"

    def test_balanced_mode(self):
        """Test balanced mode."""
        assert extract_quality_mode("chat_balanced") == "balanced"

    def test_practice_mode(self):
        """Test practice mode."""
        assert extract_quality_mode("voice_practice") == "practice"

    def test_simple_service_name(self):
        """Test simple service name returns None."""
        assert extract_quality_mode("chat") is None

    def test_empty_string(self):
        """Test empty string."""
        assert extract_quality_mode("") is None

    def test_short_kernel(self):
        """Test short kernel name like _kernel."""
        assert extract_quality_mode("_kernel") is None

    def test_very_short_kernel(self):
        """Test very short kernel name."""
        result = extract_quality_mode("_kern")
        assert result is None


# === Test PipelineContext ===

class TestPipelineContext:
    """Tests for PipelineContext class."""

    def test_default_initialization(self):
        """Test default values."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )
        assert ctx.topology is None
        assert ctx.behavior is None
        assert ctx.service == "pipeline"
        assert ctx.data == {}
        assert ctx.canceled is False
        assert ctx.artifacts == []
        assert ctx._stage_metadata == {}

    def test_with_topology(self):
        """Test with topology."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="chat_fast",
        )
        assert ctx.topology == "chat_fast"

    def test_with_behavior(self):
        """Test with behavior."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            behavior="practice",
        )
        assert ctx.behavior == "practice"

    def test_with_configuration(self):
        """Test with configuration."""
        config = {"key": "value"}
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            configuration=config,
        )
        assert ctx.configuration == config

    def test_with_custom_service(self):
        """Test with custom service name."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            service="custom_service",
        )
        assert ctx.service == "custom_service"

    def test_with_event_sink(self):
        """Test with custom event sink."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            event_sink=NoOpEventSink(),
        )
        assert ctx.event_sink is not None

    def test_with_db_session(self):
        """Test with db session."""
        db = {"connection": "test"}
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            db=db,
        )
        assert ctx.db == db

    def test_canceled_flag(self):
        """Test canceled flag."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            canceled=True,
        )
        assert ctx.canceled is True

    def test_artifacts_list(self):
        """Test artifacts list."""
        from stageflow.core.stages import StageArtifact
        artifacts = [StageArtifact(type="audio", payload={"format": "mp3"})]
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            artifacts=artifacts,
        )
        assert len(ctx.artifacts) == 1
        assert ctx.artifacts[0].type == "audio"

    def test_data_dict(self):
        """Test data dict."""
        data = {"key": "value", "number": 42}
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            data=data,
        )
        assert ctx.data == data

    def test_has_slots(self):
        """Verify PipelineContext uses slots."""
        assert hasattr(PipelineContext, "__slots__")

    # === record_stage_event tests ===

    def test_record_stage_event(self):
        """Test record_stage_event emits event."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )

        # Mock the event sink
        emitted_events = []
        class MockEventSink:
            def try_emit(self, *, type, data):
                emitted_events.append((type, data))

        ctx.event_sink = MockEventSink()

        ctx.record_stage_event(stage="test_stage", status="started")

        assert len(emitted_events) == 1
        type_, data = emitted_events[0]
        assert type_ == "stage.test_stage.started"
        assert data["stage"] == "test_stage"
        assert data["status"] == "started"

    def test_record_stage_event_with_payload(self):
        """Test record_stage_event with payload."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )

        emitted = []
        class MockEventSink:
            def try_emit(self, *, type, data):
                emitted.append(data)

        ctx.event_sink = MockEventSink()

        ctx.record_stage_event(
            stage="test_stage",
            status="completed",
            payload={"duration_ms": 1500, "output_size": 1024},
        )

        data = emitted[0]
        assert data["duration_ms"] == 1500
        assert data["output_size"] == 1024

    def test_record_stage_event_includes_context_info(self):
        """Test record_stage_event includes context info."""
        run_id = uuid4()
        req_id = uuid4()
        sess_id = uuid4()
        user_id = uuid4()
        org_id = uuid4()

        ctx = PipelineContext(
            pipeline_run_id=run_id,
            request_id=req_id,
            session_id=sess_id,
            user_id=user_id,
            org_id=org_id,
            interaction_id=uuid4(),
            topology="chat_fast",
            behavior="practice",
        )

        emitted = []
        class MockEventSink:
            def try_emit(self, *, type, data):
                emitted.append(data)

        ctx.event_sink = MockEventSink()

        ctx.record_stage_event(stage="test", status="completed")

        data = emitted[0]
        assert data["request_id"] == str(req_id)
        assert data["session_id"] == str(sess_id)
        assert data["user_id"] == str(user_id)
        assert data["org_id"] == str(org_id)
        assert data["topology"] == "chat_fast"
        assert data["behavior"] == "practice"

    def test_record_stage_event_includes_pipeline_run_id(self):
        """Test pipeline_run_id is included when present."""
        run_id = uuid4()
        ctx = PipelineContext(
            pipeline_run_id=run_id,
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )

        emitted = []
        class MockEventSink:
            def try_emit(self, *, type, data):
                emitted.append(data)

        ctx.event_sink = MockEventSink()

        ctx.record_stage_event(stage="test", status="completed")

        data = emitted[0]
        assert "pipeline_run_id" in data
        assert data["pipeline_run_id"] == str(run_id)

    def test_record_stage_event_handles_none_ids(self):
        """Test record_stage_event handles None IDs gracefully."""
        ctx = PipelineContext(
            pipeline_run_id=None,
            request_id=None,
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
        )

        emitted = []
        class MockEventSink:
            def try_emit(self, *, type, data):
                emitted.append(data)

        ctx.event_sink = MockEventSink()

        # Should not raise
        ctx.record_stage_event(stage="test", status="completed")

        data = emitted[0]
        assert data["request_id"] is None
        assert data["session_id"] is None

    # === set_stage_metadata tests ===

    def test_set_stage_metadata(self):
        """Test set_stage_metadata."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )

        ctx.set_stage_metadata("stage1", {"duration": 100})
        assert ctx._stage_metadata["stage1"] == {"duration": 100}

    def test_get_stage_metadata(self):
        """Test get_stage_metadata."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )

        ctx._stage_metadata["stage1"] = {"duration": 100}
        metadata = ctx.get_stage_metadata("stage1")
        assert metadata == {"duration": 100}

    def test_get_stage_metadata_missing(self):
        """Test get_stage_metadata returns None for missing."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )

        assert ctx.get_stage_metadata("missing") is None

    def test_overwrite_stage_metadata(self):
        """Test overwriting stage metadata."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )

        ctx.set_stage_metadata("stage1", {"v": 1})
        ctx.set_stage_metadata("stage1", {"v": 2})
        assert ctx.get_stage_metadata("stage1") == {"v": 2}

    # === to_dict tests ===

    def test_to_dict(self):
        """Test to_dict converts context to dict."""
        run_id = uuid4()
        req_id = uuid4()
        sess_id = uuid4()
        user_id = uuid4()
        org_id = uuid4()
        int_id = uuid4()

        ctx = PipelineContext(
            pipeline_run_id=run_id,
            request_id=req_id,
            session_id=sess_id,
            user_id=user_id,
            org_id=org_id,
            interaction_id=int_id,
            topology="chat_fast",
            behavior="practice",
            data={"key": "value"},
        )

        result = ctx.to_dict()

        assert result["pipeline_run_id"] == str(run_id)
        assert result["request_id"] == str(req_id)
        assert result["session_id"] == str(sess_id)
        assert result["user_id"] == str(user_id)
        assert result["org_id"] == str(org_id)
        assert result["interaction_id"] == str(int_id)
        assert result["topology"] == "chat_fast"
        assert result["behavior"] == "practice"
        assert result["data"] == {"key": "value"}
        assert result["canceled"] is False
        assert result["artifacts_count"] == 0

    def test_to_dict_handles_none_uuids(self):
        """Test to_dict handles None UUIDs."""
        ctx = PipelineContext(
            pipeline_run_id=None,
            request_id=None,
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
        )

        result = ctx.to_dict()

        assert result["pipeline_run_id"] is None
        assert result["request_id"] is None

    def test_to_dict_counts_artifacts(self):
        """Test to_dict includes artifact count."""
        from stageflow.core.stages import StageArtifact
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            artifacts=[
                StageArtifact(type="a", payload={}),
                StageArtifact(type="b", payload={}),
            ],
        )

        result = ctx.to_dict()

        assert result["artifacts_count"] == 2

    def test_to_dict_includes_service(self):
        """Test to_dict includes service."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            service="custom",
        )

        result = ctx.to_dict()

        assert result["service"] == "custom"

    # === now() classmethod tests ===

    def test_now_returns_datetime(self):
        """Test now() returns datetime."""
        now = PipelineContext.now()
        assert isinstance(now, datetime)
        assert now.tzinfo is not None

    def test_now_is_utc(self):
        """Test now() returns UTC datetime."""
        now = PipelineContext.now()
        assert now.tzinfo == UTC

    def test_now_is_recent(self):
        """Test now() returns recent time."""
        before = datetime.now(UTC)
        now = PipelineContext.now()
        after = datetime.now(UTC)

        assert before <= now <= after


# === Edge Cases ===

class TestPipelineContextEdgeCases:
    """Edge case tests for PipelineContext."""

    def test_empty_configuration(self):
        """Test with empty configuration."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            configuration={},
        )
        assert ctx.configuration == {}

    def test_complex_data(self):
        """Test with complex nested data."""
        data = {
            "nested": {"a": {"b": "c"}},
            "list": [1, 2, 3],
            "mixed": {"list": [{"key": "value"}]},
        }
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            data=data,
        )
        assert ctx.data == data

    def test_many_artifacts(self):
        """Test with many artifacts."""
        artifacts = [
            {"type": f"type_{i}", "payload": {"id": i}}
            for i in range(100)
        ]
        from stageflow.core.stages import StageArtifact
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            artifacts=[StageArtifact(type=a["type"], payload=a["payload"]) for a in artifacts],
        )
        assert len(ctx.artifacts) == 100

    def test_many_stage_metadata(self):
        """Test with many stage metadata entries."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )

        for i in range(50):
            ctx.set_stage_metadata(f"stage_{i}", {"order": i})

        assert len(ctx._stage_metadata) == 50

    def test_event_sink_with_emit(self):
        """Test event sink with async emit method."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        )

        emitted = []
        class AsyncEventSink:
            async def emit(self, *, type, data):
                emitted.append((type, data))

            def try_emit(self, *, type, data):
                # Should prefer try_emit if available
                emitted.append((type, data))

        ctx.event_sink = AsyncEventSink()
        ctx.record_stage_event(stage="test", status="completed")
        assert len(emitted) == 1
