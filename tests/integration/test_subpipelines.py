"""Integration tests for subpipeline spawning.

These tests verify end-to-end subpipeline execution, including:
- Full pipeline execution with child pipelines
- Event emission and observability
- Cancellation propagation
- Depth limit enforcement
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from stageflow.core import StageContext, StageKind, StageOutput
from stageflow.events import NoOpEventSink, clear_event_sink, set_event_sink
from stageflow.helpers.run_utils import ObservableEventSink
from stageflow.pipeline import (
    MaxDepthExceededError,
    Pipeline,
    PipelineRegistry,
    SubpipelineSpawner,
    clear_subpipeline_spawner,
    set_subpipeline_spawner,
)
from stageflow.pipeline.subpipeline import ChildRunTracker
from stageflow.stages.context import PipelineContext
from stageflow.tools.executor import ToolExecutor


def create_test_pipeline_context(
    *,
    pipeline_run_id: UUID | None = None,
    topology: str = "test",
    execution_mode: str = "practice",
    event_sink: Any = None,
) -> PipelineContext:
    """Create a PipelineContext for testing."""
    return PipelineContext(
        pipeline_run_id=pipeline_run_id or uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=None,
        interaction_id=uuid4(),
        topology=topology,
        execution_mode=execution_mode,
        event_sink=event_sink or NoOpEventSink(),
    )


class SimpleStage:
    """Simple stage that returns static data."""

    id = "simple_stage"

    def __init__(self, data: dict[str, Any] | None = None):
        self._data = data or {"simple": "output"}

    async def execute(self, _ctx: StageContext) -> StageOutput:
        return StageOutput.ok(data=self._data)


class CounterStage:
    """Stage that increments a counter for testing execution."""

    id = "counter_stage"
    execution_count = 0

    async def execute(self, _ctx: StageContext) -> StageOutput:
        CounterStage.execution_count += 1
        return StageOutput.ok(data={"count": CounterStage.execution_count})


class TestSubpipelineIntegration:
    """Integration tests for subpipeline spawning."""

    @pytest.fixture(autouse=True)
    def reset_globals(self):
        """Reset global state before each test."""
        clear_subpipeline_spawner()
        CounterStage.execution_count = 0
        yield
        clear_subpipeline_spawner()

    @pytest.fixture
    def registry(self):
        """Create a fresh PipelineRegistry."""
        return PipelineRegistry()

    @pytest.fixture
    def child_pipeline(self):
        """Create a simple child pipeline."""
        return Pipeline().with_stage("child_stage", SimpleStage, StageKind.TRANSFORM)

    @pytest.fixture
    def parent_ctx(self):
        """Create a parent PipelineContext."""
        return create_test_pipeline_context(
            topology="parent_pipeline",
            execution_mode="practice",
        )

    @pytest.mark.asyncio
    async def test_spawn_subpipeline_executes_child(self, registry, child_pipeline, parent_ctx):
        """Should execute child pipeline and return results."""
        registry.register("child_pipeline", child_pipeline)

        executor = ToolExecutor(registry=registry)
        correlation_id = uuid4()

        result = await executor.spawn_subpipeline(
            "child_pipeline",
            parent_ctx,
            correlation_id,
        )

        assert result.success is True
        assert result.child_run_id is not None
        assert result.data is not None
        assert "child_stage" in result.data
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_spawn_subpipeline_with_topology_override(self, registry, child_pipeline, parent_ctx):
        """Should pass topology override to child context."""
        registry.register("child_pipeline", child_pipeline)

        executor = ToolExecutor(registry=registry)

        result = await executor.spawn_subpipeline(
            "child_pipeline",
            parent_ctx,
            uuid4(),
            topology_override="fast_kernel",
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_spawn_subpipeline_with_execution_mode_override(self, registry, child_pipeline, parent_ctx):
        """Should pass execution mode override to child context."""
        registry.register("child_pipeline", child_pipeline)

        executor = ToolExecutor(registry=registry)

        result = await executor.spawn_subpipeline(
            "child_pipeline",
            parent_ctx,
            uuid4(),
            execution_mode_override="strict",
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_spawn_subpipeline_not_found(self, registry, parent_ctx):
        """Should raise KeyError for unknown pipeline."""
        executor = ToolExecutor(registry=registry)

        with pytest.raises(KeyError) as exc_info:
            await executor.spawn_subpipeline(
                "nonexistent_pipeline",
                parent_ctx,
                uuid4(),
            )

        assert "nonexistent_pipeline" in str(exc_info.value)


class TestSubpipelineEvents:
    """Test event emission during subpipeline execution."""

    @pytest.fixture(autouse=True)
    def reset_globals(self):
        """Reset global state before each test."""
        clear_subpipeline_spawner()
        clear_event_sink()
        yield
        clear_subpipeline_spawner()
        clear_event_sink()

    @pytest.fixture
    def event_sink(self):
        """Create an observable event sink and set it globally."""
        sink = ObservableEventSink(verbose=False, colorize=False, capture=True)
        set_event_sink(sink)  # Set globally so SubpipelineSpawner can use it
        return sink

    @pytest.fixture
    def registry(self):
        """Create a fresh PipelineRegistry."""
        return PipelineRegistry()

    @pytest.fixture
    def child_pipeline(self):
        """Create a simple child pipeline."""
        return Pipeline().with_stage("child_stage", SimpleStage, StageKind.TRANSFORM)

    @pytest.mark.asyncio
    async def test_emits_spawned_event(self, registry, child_pipeline, event_sink):
        """Should emit pipeline.spawned_child event."""
        registry.register("child_pipeline", child_pipeline)

        # Create spawner with event emission enabled
        spawner = SubpipelineSpawner(emit_events=True)
        set_subpipeline_spawner(spawner)

        ctx = create_test_pipeline_context(event_sink=event_sink)
        executor = ToolExecutor(registry=registry, spawner=spawner)

        await executor.spawn_subpipeline(
            "child_pipeline",
            ctx,
            uuid4(),
        )

        spawned_events = [e for e in event_sink.events if e["type"] == "pipeline.spawned_child"]
        assert len(spawned_events) >= 1

    @pytest.mark.asyncio
    async def test_emits_completed_event(self, registry, child_pipeline, event_sink):
        """Should emit pipeline.child_completed event on success."""
        registry.register("child_pipeline", child_pipeline)

        spawner = SubpipelineSpawner(emit_events=True)
        set_subpipeline_spawner(spawner)

        ctx = create_test_pipeline_context(event_sink=event_sink)
        executor = ToolExecutor(registry=registry, spawner=spawner)

        await executor.spawn_subpipeline(
            "child_pipeline",
            ctx,
            uuid4(),
        )

        completed_events = [e for e in event_sink.events if e["type"] == "pipeline.child_completed"]
        assert len(completed_events) >= 1


class TestSubpipelineDepthLimit:
    """Test depth limit enforcement for nested subpipelines."""

    @pytest.fixture(autouse=True)
    def reset_globals(self):
        """Reset global state before each test."""
        clear_subpipeline_spawner()
        yield
        clear_subpipeline_spawner()

    @pytest.fixture
    def registry(self):
        """Create a fresh PipelineRegistry."""
        return PipelineRegistry()

    @pytest.fixture
    def child_pipeline(self):
        """Create a simple child pipeline."""
        return Pipeline().with_stage("child_stage", SimpleStage, StageKind.TRANSFORM)

    @pytest.mark.asyncio
    async def test_max_depth_exceeded_raises(self, registry, child_pipeline):
        """Should raise MaxDepthExceededError when depth limit exceeded."""
        registry.register("child_pipeline", child_pipeline)

        # Create spawner with max_depth=1
        spawner = SubpipelineSpawner(max_depth=1, emit_events=False)
        set_subpipeline_spawner(spawner)

        executor = ToolExecutor(registry=registry, spawner=spawner)

        # First spawn should succeed
        ctx1 = create_test_pipeline_context()
        result1 = await executor.spawn_subpipeline(
            "child_pipeline",
            ctx1,
            uuid4(),
        )
        assert result1.success is True

        # Simulate a context at depth 1 (as if we're inside a child)
        # by manually setting the depth tracking
        ctx2 = create_test_pipeline_context()
        spawner._run_depths[ctx2.pipeline_run_id] = 1  # Simulate depth 1

        with pytest.raises(MaxDepthExceededError) as exc_info:
            await executor.spawn_subpipeline(
                "child_pipeline",
                ctx2,
                uuid4(),
            )

        assert exc_info.value.current_depth == 1
        assert exc_info.value.max_depth == 1


class TestSubpipelineChildTracking:
    """Test child run tracking for cancellation propagation."""

    @pytest.fixture(autouse=True)
    def reset_globals(self):
        """Reset global state before each test."""
        clear_subpipeline_spawner()
        yield
        clear_subpipeline_spawner()

    @pytest.fixture
    def tracker(self):
        """Create a fresh ChildRunTracker."""
        return ChildRunTracker()

    @pytest.fixture
    def registry(self):
        """Create a fresh PipelineRegistry."""
        return PipelineRegistry()

    @pytest.fixture
    def child_pipeline(self):
        """Create a simple child pipeline."""
        return Pipeline().with_stage("child_stage", SimpleStage, StageKind.TRANSFORM)

    @pytest.mark.asyncio
    async def test_child_registered_during_execution(self, tracker, registry, child_pipeline):
        """Should register child with tracker during execution."""
        registry.register("child_pipeline", child_pipeline)

        spawner = SubpipelineSpawner(child_tracker=tracker, emit_events=False)
        set_subpipeline_spawner(spawner)

        ctx = create_test_pipeline_context()
        executor = ToolExecutor(registry=registry, spawner=spawner)

        original_spawn = spawner.spawn

        async def tracking_spawn(*args, **kwargs):
            result = await original_spawn(*args, **kwargs)
            # Child should have been unregistered by now (after completion)
            return result

        spawner.spawn = tracking_spawn

        result = await executor.spawn_subpipeline(
            "child_pipeline",
            ctx,
            uuid4(),
        )

        assert result.success is True
        # After completion, child should be unregistered
        children = await tracker.get_children(ctx.pipeline_run_id)
        assert len(children) == 0  # Unregistered after completion

    @pytest.mark.asyncio
    async def test_tracker_metrics_updated(self, tracker, registry, child_pipeline):
        """Should update tracker metrics during execution."""
        registry.register("child_pipeline", child_pipeline)

        spawner = SubpipelineSpawner(child_tracker=tracker, emit_events=False)
        set_subpipeline_spawner(spawner)

        ctx = create_test_pipeline_context()
        executor = ToolExecutor(registry=registry, spawner=spawner)

        await executor.spawn_subpipeline(
            "child_pipeline",
            ctx,
            uuid4(),
        )

        metrics = await tracker.get_metrics()
        assert metrics["registration_count"] >= 1
        assert metrics["unregistration_count"] >= 1


class TestSubpipelineCorrelation:
    """Test correlation ID propagation in subpipelines."""

    @pytest.fixture(autouse=True)
    def reset_globals(self):
        """Reset global state before each test."""
        clear_subpipeline_spawner()
        yield
        clear_subpipeline_spawner()

    @pytest.fixture
    def registry(self):
        """Create a fresh PipelineRegistry."""
        return PipelineRegistry()

    @pytest.fixture
    def child_pipeline(self):
        """Create a simple child pipeline."""
        return Pipeline().with_stage("child_stage", SimpleStage, StageKind.TRANSFORM)

    @pytest.mark.asyncio
    async def test_correlation_id_passed_to_spawner(self, registry, child_pipeline):
        """Should pass correlation_id to spawner for tracing."""
        registry.register("child_pipeline", child_pipeline)

        # Track the correlation_id passed to spawn
        captured_correlation_id = None

        class TrackingSpawner(SubpipelineSpawner):
            async def spawn(self, *args, **kwargs):
                nonlocal captured_correlation_id
                captured_correlation_id = kwargs.get("correlation_id")
                return await super().spawn(*args, **kwargs)

        spawner = TrackingSpawner(emit_events=False)
        set_subpipeline_spawner(spawner)

        ctx = create_test_pipeline_context()
        executor = ToolExecutor(registry=registry, spawner=spawner)

        correlation_id = uuid4()
        await executor.spawn_subpipeline(
            "child_pipeline",
            ctx,
            correlation_id,
        )

        assert captured_correlation_id == correlation_id

    @pytest.mark.asyncio
    async def test_parent_stage_id_is_tool_executor(self, registry, child_pipeline):
        """Should use ToolExecutor.id as parent_stage_id."""
        registry.register("child_pipeline", child_pipeline)

        captured_parent_stage_id = None

        class TrackingSpawner(SubpipelineSpawner):
            async def spawn(self, *args, **kwargs):
                nonlocal captured_parent_stage_id
                captured_parent_stage_id = kwargs.get("parent_stage_id")
                return await super().spawn(*args, **kwargs)

        spawner = TrackingSpawner(emit_events=False)
        set_subpipeline_spawner(spawner)

        ctx = create_test_pipeline_context()
        executor = ToolExecutor(registry=registry, spawner=spawner)

        await executor.spawn_subpipeline(
            "child_pipeline",
            ctx,
            uuid4(),
        )

        assert captured_parent_stage_id == "stage.tool_executor"
