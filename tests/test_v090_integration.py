"""Integration tests for Stageflow v0.9.0 features.

Tests the integration of new v0.9.0 modules with the core framework,
including StageContext event handling, ContextSnapshot usage, and
production pipeline patterns.
"""

import asyncio
from uuid import uuid4

import pytest

from stageflow import PipelineTimer, StageContext, StageKind, StageOutput
from stageflow.context import ContextSnapshot, RunIdentity
from stageflow.core.stage_context import create_stage_context
from stageflow.stages import StageInputs


class MockEventSink:
    """Mock event sink for testing."""

    def __init__(self):
        self.events = []

    def try_emit(self, type: str, data: dict):
        self.events.append({"type": type, "data": data})


class TestStageContextEventHandling:
    """Test StageContext event handling capabilities."""

    def test_stage_context_has_event_sink_field(self):
        """Verify StageContext has event_sink field."""
        snapshot = ContextSnapshot(
            run_id=RunIdentity(
                pipeline_run_id=uuid4(),
                request_id=uuid4(),
                session_id=uuid4(),
                user_id=uuid4(),
                org_id=None,
                interaction_id=uuid4(),
            ),
            topology="test",
            execution_mode="test",
        )

        ctx = StageContext(
            snapshot=snapshot,
            inputs=StageInputs(snapshot=snapshot),
            stage_name="test_stage",
            timer=PipelineTimer(),
            event_sink=None,
        )

        assert hasattr(ctx, "event_sink")
        assert ctx.event_sink is None

    def test_stage_context_with_event_sink(self):
        """Verify StageContext can be created with event_sink."""
        event_sink = MockEventSink()
        snapshot = ContextSnapshot(
            run_id=RunIdentity(
                pipeline_run_id=uuid4(),
                request_id=uuid4(),
                session_id=uuid4(),
                user_id=uuid4(),
                org_id=None,
                interaction_id=uuid4(),
            ),
            topology="test",
            execution_mode="test",
        )

        ctx = StageContext(
            snapshot=snapshot,
            inputs=StageInputs(snapshot=snapshot),
            stage_name="test_stage",
            timer=PipelineTimer(),
            event_sink=event_sink,
        )

        assert ctx.event_sink is event_sink

    def test_try_emit_event_with_sink(self):
        """Verify try_emit_event works with event sink."""
        event_sink = MockEventSink()
        snapshot = ContextSnapshot(
            run_id=RunIdentity(
                pipeline_run_id=uuid4(),
                request_id=uuid4(),
                session_id=uuid4(),
                user_id=uuid4(),
                org_id=None,
                interaction_id=uuid4(),
            ),
            topology="test",
            execution_mode="test",
        )

        ctx = StageContext(
            snapshot=snapshot,
            inputs=StageInputs(snapshot=snapshot),
            stage_name="test_stage",
            timer=PipelineTimer(),
            event_sink=event_sink,
        )

        ctx.try_emit_event("test.event", {"key": "value"})

        assert len(event_sink.events) == 1
        assert event_sink.events[0]["type"] == "test.event"
        assert event_sink.events[0]["data"]["key"] == "value"

    def test_try_emit_event_without_sink(self):
        """Verify try_emit_event works without event sink (logs debug)."""
        snapshot = ContextSnapshot(
            run_id=RunIdentity(
                pipeline_run_id=uuid4(),
                request_id=uuid4(),
                session_id=uuid4(),
                user_id=uuid4(),
                org_id=None,
                interaction_id=uuid4(),
            ),
            topology="test",
            execution_mode="test",
        )

        ctx = StageContext(
            snapshot=snapshot,
            inputs=StageInputs(snapshot=snapshot),
            stage_name="test_stage",
            timer=PipelineTimer(),
            event_sink=None,
        )

        # Should not raise, just log
        ctx.try_emit_event("test.event", {"key": "value"})

    def test_record_stage_event(self):
        """Verify record_stage_event method works."""
        event_sink = MockEventSink()
        snapshot = ContextSnapshot(
            run_id=RunIdentity(
                pipeline_run_id=uuid4(),
                request_id=uuid4(),
                session_id=uuid4(),
                user_id=uuid4(),
                org_id=None,
                interaction_id=uuid4(),
            ),
            topology="test",
            execution_mode="test",
        )

        ctx = StageContext(
            snapshot=snapshot,
            inputs=StageInputs(snapshot=snapshot),
            stage_name="test_stage",
            timer=PipelineTimer(),
            event_sink=event_sink,
        )

        ctx.record_stage_event("my_stage", "started", duration_ms=100)

        assert len(event_sink.events) == 1
        assert event_sink.events[0]["type"] == "stage.started"
        assert event_sink.events[0]["data"]["stage"] == "my_stage"
        assert event_sink.events[0]["data"]["duration_ms"] == 100


class TestContextSnapshot:
    """Test ContextSnapshot creation and usage."""

    def test_context_snapshot_with_run_identity(self):
        """Verify ContextSnapshot requires RunIdentity."""
        run_id = RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=None,
            interaction_id=uuid4(),
        )

        snapshot = ContextSnapshot(
            run_id=run_id,
            topology="test",
            execution_mode="test",
        )

        assert snapshot.run_id == run_id
        assert snapshot.topology == "test"
        assert snapshot.execution_mode == "test"

    def test_context_snapshot_with_input_data(self):
        """Verify ContextSnapshot accepts input data fields."""
        run_id = RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=None,
            interaction_id=uuid4(),
        )

        snapshot = ContextSnapshot(
            run_id=run_id,
            topology="test",
            execution_mode="test",
            input_text="Hello, World!",
        )

        assert snapshot.input_text == "Hello, World!"

    def test_context_snapshot_pipeline_run_id_property(self):
        """Verify pipeline_run_id property works."""
        run_id = RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=None,
            interaction_id=uuid4(),
        )

        snapshot = ContextSnapshot(
            run_id=run_id,
            topology="test",
            execution_mode="test",
        )

        assert snapshot.pipeline_run_id == run_id.pipeline_run_id


class TestVersionMetadataAPI:
    """Test VersionMetadata.create() API."""

    def test_version_metadata_create_with_version(self):
        """Verify VersionMetadata.create() requires version parameter."""
        from stageflow.context.enrich import VersionMetadata

        version = VersionMetadata.create(
            content_id="test_content",
            version="1.0.0",
            source="test",
            content="test content",
            ttl_seconds=3600,
            tags=["test", "v1"],
        )

        assert version.content_id == "test_content"
        assert version.version == "1.0.0"
        assert version.source == "test"
        assert version.checksum is not None
        assert version.ttl_seconds == 3600
        assert "test" in version.tags
        assert "v1" in version.tags

    def test_version_metadata_create_without_content(self):
        """Verify VersionMetadata.create() works without content."""
        from stageflow.context.enrich import VersionMetadata

        version = VersionMetadata.create(
            content_id="test_content",
            version="1.0.0",
            source="test",
        )

        assert version.content_id == "test_content"
        assert version.version == "1.0.0"
        assert version.checksum is None  # No content, no checksum

    def test_version_metadata_is_stale(self):
        """Verify is_stale property works."""
        from stageflow.context.enrich import VersionMetadata

        # Create version with 1 second TTL
        version = VersionMetadata.create(
            content_id="test_content",
            version="1.0.0",
            source="test",
            ttl_seconds=1,
        )

        assert version.is_stale is False  # Just created


class TestPipelineBuilderIntegration:
    """Test pipeline builder integration with v0.9.0 features."""

    @pytest.mark.asyncio
    async def test_fluent_pipeline_builder_with_event_sink(self):
        """Verify FluentPipelineBuilder works with event sink."""
        from stageflow.pipeline.builder_helpers import FluentPipelineBuilder

        event_sink = MockEventSink()

        builder = FluentPipelineBuilder("test_pipeline")
        builder.stage("stage1", TestStage("stage1", delay=0.01))
        builder.stage("stage2", TestStage("stage2", delay=0.01), depends_on=("stage1",))

        pipeline = builder.build()

        run_id = RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=None,
            interaction_id=uuid4(),
        )

        snapshot = ContextSnapshot(
            run_id=run_id,
            topology="test",
            execution_mode="test",
        )

        ctx = create_stage_context(
            snapshot=snapshot,
            inputs=StageInputs(snapshot=snapshot),
            stage_name="pipeline_entry",
            timer=PipelineTimer(),
            event_sink=event_sink,
        )

        results = await pipeline.run(ctx)

        assert results["stage1"].success
        assert results["stage2"].success


class TestRetryInterceptorIntegration:
    """Test RetryInterceptor integration."""

    @pytest.mark.asyncio
    async def test_retry_interceptor_with_pipeline(self):
        """Verify RetryInterceptor works with pipeline execution."""
        from stageflow.pipeline.builder_helpers import FluentPipelineBuilder
        from stageflow.pipeline.interceptors import get_default_interceptors
        from stageflow.pipeline.retry import BackoffStrategy, JitterStrategy, RetryInterceptor

        # Create a stage that fails once then succeeds
        call_count = 0

        class FlakyStage:
            name = "flaky"
            kind = StageKind.TRANSFORM

            async def execute(self, _ctx):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise ConnectionError("First attempt fails")
                return StageOutput.ok(data={"attempt": call_count})

        builder = FluentPipelineBuilder("retry_test")
        builder.stage("flaky", FlakyStage())

        pipeline = builder.build()

        run_id = RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=None,
            interaction_id=uuid4(),
        )

        snapshot = ContextSnapshot(
            run_id=run_id,
            topology="test",
            execution_mode="test",
        )

        ctx = create_stage_context(
            snapshot=snapshot,
            inputs=StageInputs(snapshot=snapshot),
            stage_name="pipeline_entry",
            timer=PipelineTimer(),
        )

        # Setup interceptors with retry
        interceptors = get_default_interceptors()
        retry_interceptor = RetryInterceptor(
            max_attempts=3,
            base_delay_ms=10,
            backoff_strategy=BackoffStrategy.CONSTANT,
            jitter_strategy=JitterStrategy.NONE,
            retryable_errors=(ConnectionError,),
        )
        interceptors.append(retry_interceptor)

        # Reset call count
        call_count = 0

        results = await pipeline.run(ctx, interceptors=interceptors)

        assert results["flaky"].success
        assert results["flaky"].data["attempt"] == 2  # Failed once, succeeded on retry


class TestEnrichUtilitiesIntegration:
    """Test ENRICH utilities integration."""

    def test_context_utilization_integration(self):
        """Verify ContextUtilization works in context."""
        from stageflow.context.enrich import ContextUtilization

        util = ContextUtilization(max_tokens=1000, used_tokens=500)

        assert util.utilization == 0.5
        assert util.is_near_limit is False

        util.used_tokens = 900
        assert util.utilization == 0.9
        assert util.is_near_limit is True

    def test_truncation_tracker_integration(self):
        """Verify TruncationTracker emits events."""
        from stageflow.context.enrich import TruncationTracker

        event_sink = MockEventSink()
        tracker = TruncationTracker(event_sink)

        event = tracker.record_truncation(1000, 500, "tail", "document", "limit")

        assert event.original_tokens == 1000
        assert event.truncated_tokens == 500
        assert len(event_sink.events) == 1
        assert "truncation" in event_sink.events[0]["type"]

    def test_conflict_detector_integration(self):
        """Verify ConflictDetector resolves conflicts."""
        from stageflow.context.enrich import ConflictDetector, ConflictResolution
        
        detector = ConflictDetector()
        
        # Test keep_new strategy
        result = detector.check_and_resolve(
            "test_field",
            {"key": "old"},
            {"key": "new"},
        )
        assert result.resolution == "keep_new"
        assert result.merged_value == {"key": "new"}
        
        # Test keep_old strategy
        detector_old = ConflictDetector(default_strategy="keep_old")
        result = detector_old.check_and_resolve(
            "test_field",
            {"key": "old"},
            {"key": "new"},
        )
        assert result.resolution == "keep_old"
        assert result.merged_value == {"key": "old"}


# Helper class for tests
class TestStage:
    """Test stage for integration tests."""

    def __init__(self, name: str, delay: float = 0.01):
        self.name = name
        self.kind = StageKind.TRANSFORM
        self.delay = delay

    async def execute(self, _ctx: StageContext) -> StageOutput:
        """Execute the test stage."""
        await asyncio.sleep(self.delay)
        return StageOutput.ok(data={"stage": self.name})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
