"""Unit tests for subpipeline spawning and child tracking."""

from __future__ import annotations

from uuid import uuid4

import pytest

from stageflow.pipeline.subpipeline import (
    ChildRunTracker,
    PipelineCanceledEvent,
    PipelineChildCompletedEvent,
    PipelineChildFailedEvent,
    PipelineSpawnedChildEvent,
    SubpipelineResult,
    clear_child_tracker,
    get_child_tracker,
)


class TestSubpipelineResult:
    """Tests for SubpipelineResult dataclass."""

    def test_create_success_result(self) -> None:
        """Create a successful SubpipelineResult."""
        child_run_id = uuid4()
        result = SubpipelineResult(
            success=True,
            child_run_id=child_run_id,
            data={"key": "value"},
            duration_ms=150.5,
        )

        assert result.success is True
        assert result.child_run_id == child_run_id
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_create_failure_result(self) -> None:
        """Create a failed SubpipelineResult."""
        result = SubpipelineResult(
            success=False,
            child_run_id=uuid4(),
            error="Pipeline failed",
            duration_ms=50.0,
        )

        assert result.success is False
        assert result.error == "Pipeline failed"

    def test_result_to_dict(self) -> None:
        """SubpipelineResult serializes to dictionary."""
        child_run_id = uuid4()
        result = SubpipelineResult(
            success=True,
            child_run_id=child_run_id,
            data={"result": "done"},
            duration_ms=100.0,
        )

        d = result.to_dict()
        assert d["success"] is True
        assert d["child_run_id"] == str(child_run_id)
        assert d["data"] == {"result": "done"}
        assert d["duration_ms"] == 100.0


class TestChildRunTracker:
    """Tests for ChildRunTracker."""

    @pytest.fixture
    def tracker(self) -> ChildRunTracker:
        """Create a fresh tracker for each test."""
        return ChildRunTracker()

    @pytest.mark.asyncio
    async def test_register_and_get_children(self, tracker: ChildRunTracker) -> None:
        """Register children and retrieve them."""
        parent_id = uuid4()
        child1 = uuid4()
        child2 = uuid4()

        await tracker.register_child(parent_id, child1)
        await tracker.register_child(parent_id, child2)

        children = await tracker.get_children(parent_id)

        assert child1 in children
        assert child2 in children
        assert len(children) == 2

    @pytest.mark.asyncio
    async def test_get_children_empty(self, tracker: ChildRunTracker) -> None:
        """get_children() returns empty set for unknown parent."""
        children = await tracker.get_children(uuid4())
        assert children == set()

    @pytest.mark.asyncio
    async def test_unregister_child(self, tracker: ChildRunTracker) -> None:
        """Unregister removes child from parent's set."""
        parent_id = uuid4()
        child_id = uuid4()

        await tracker.register_child(parent_id, child_id)
        await tracker.unregister_child(parent_id, child_id)

        children = await tracker.get_children(parent_id)
        assert child_id not in children

    @pytest.mark.asyncio
    async def test_get_parent(self, tracker: ChildRunTracker) -> None:
        """get_parent() returns the parent of a child."""
        parent_id = uuid4()
        child_id = uuid4()

        await tracker.register_child(parent_id, child_id)

        parent = await tracker.get_parent(child_id)
        assert parent == parent_id

    @pytest.mark.asyncio
    async def test_get_parent_none_for_root(self, tracker: ChildRunTracker) -> None:
        """get_parent() returns None for root runs."""
        parent = await tracker.get_parent(uuid4())
        assert parent is None

    @pytest.mark.asyncio
    async def test_get_all_descendants(self, tracker: ChildRunTracker) -> None:
        """get_all_descendants() returns all children recursively."""
        root = uuid4()
        child1 = uuid4()
        child2 = uuid4()
        grandchild1 = uuid4()
        grandchild2 = uuid4()

        await tracker.register_child(root, child1)
        await tracker.register_child(root, child2)
        await tracker.register_child(child1, grandchild1)
        await tracker.register_child(child2, grandchild2)

        descendants = await tracker.get_all_descendants(root)

        assert child1 in descendants
        assert child2 in descendants
        assert grandchild1 in descendants
        assert grandchild2 in descendants
        assert len(descendants) == 4

    @pytest.mark.asyncio
    async def test_get_root_run(self, tracker: ChildRunTracker) -> None:
        """get_root_run() traverses to top of tree."""
        root = uuid4()
        child = uuid4()
        grandchild = uuid4()

        await tracker.register_child(root, child)
        await tracker.register_child(child, grandchild)

        assert await tracker.get_root_run(grandchild) == root
        assert await tracker.get_root_run(child) == root
        assert await tracker.get_root_run(root) == root

    @pytest.mark.asyncio
    async def test_cleanup_run(self, tracker: ChildRunTracker) -> None:
        """cleanup_run() removes tracking data."""
        parent = uuid4()
        child = uuid4()

        await tracker.register_child(parent, child)
        await tracker.cleanup_run(child)

        assert await tracker.get_parent(child) is None
        assert child not in await tracker.get_children(parent)


class TestChildTrackerGlobals:
    """Tests for global child tracker functions."""

    def teardown_method(self) -> None:
        clear_child_tracker()

    def test_get_child_tracker_singleton(self) -> None:
        """get_child_tracker() returns same instance."""
        tracker1 = get_child_tracker()
        tracker2 = get_child_tracker()
        assert tracker1 is tracker2

    def test_clear_child_tracker(self) -> None:
        """clear_child_tracker() resets singleton."""
        tracker1 = get_child_tracker()
        clear_child_tracker()
        tracker2 = get_child_tracker()
        assert tracker1 is not tracker2


class TestSubpipelineEvents:
    """Tests for subpipeline event dataclasses."""

    def test_spawned_child_event(self) -> None:
        """PipelineSpawnedChildEvent serializes correctly."""
        event = PipelineSpawnedChildEvent(
            parent_run_id=uuid4(),
            child_run_id=uuid4(),
            parent_stage_id="tool_executor",
            pipeline_name="document_edit",
            correlation_id=uuid4(),
        )

        d = event.to_dict()
        assert "parent_run_id" in d
        assert "child_run_id" in d
        assert d["pipeline_name"] == "document_edit"

    def test_child_completed_event(self) -> None:
        """PipelineChildCompletedEvent serializes correctly."""
        event = PipelineChildCompletedEvent(
            parent_run_id=uuid4(),
            child_run_id=uuid4(),
            pipeline_name="search",
            duration_ms=250.0,
        )

        d = event.to_dict()
        assert d["duration_ms"] == 250.0

    def test_child_failed_event(self) -> None:
        """PipelineChildFailedEvent serializes correctly."""
        event = PipelineChildFailedEvent(
            parent_run_id=uuid4(),
            child_run_id=uuid4(),
            pipeline_name="risky_op",
            error_message="Something went wrong",
        )

        d = event.to_dict()
        assert d["error_message"] == "Something went wrong"

    def test_canceled_event(self) -> None:
        """PipelineCanceledEvent serializes correctly."""
        event = PipelineCanceledEvent(
            pipeline_run_id=uuid4(),
            parent_run_id=uuid4(),
            reason="user_requested",
            cascade_depth=2,
        )

        d = event.to_dict()
        assert d["reason"] == "user_requested"
        assert d["cascade_depth"] == 2
