"""Tests for ChildRunTracker metrics functionality.

Tests:
- ChildRunTracker metrics tracking
- get_metrics() method
- reset_metrics() method
- ChildTrackerMetricsInterceptor
- Integration with default interceptors
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest

from stageflow.pipeline.subpipeline import (
    ChildRunTracker,
    get_child_tracker,
    set_child_tracker,
    clear_child_tracker,
)
from stageflow.pipeline.interceptors import (
    ChildTrackerMetricsInterceptor,
    get_default_interceptors,
)
from stageflow.core import StageStatus
from stageflow.stages.context import PipelineContext
from stageflow.context import ContextSnapshot
from stageflow.stages.result import StageResult


class TestChildRunTrackerMetrics:
    """Tests for ChildRunTracker metrics functionality."""

    async def test_initial_metrics(self):
        """Test initial metrics state."""
        tracker = ChildRunTracker()
        metrics = await tracker.get_metrics()
        
        assert metrics["registration_count"] == 0
        assert metrics["unregistration_count"] == 0
        assert metrics["lookup_count"] == 0
        assert metrics["tree_traversal_count"] == 0
        assert metrics["cleanup_count"] == 0
        assert metrics["max_concurrent_children"] == 0
        assert metrics["max_depth_seen"] == 0
        assert metrics["active_parents"] == 0
        assert metrics["active_children"] == 0
        assert metrics["total_relationships"] == 0

    async def test_registration_metrics(self):
        """Test registration metrics tracking."""
        tracker = ChildRunTracker()
        parent_id = uuid4()
        child_id = uuid4()
        
        await tracker.register_child(parent_id, child_id)
        metrics = await tracker.get_metrics()
        
        assert metrics["registration_count"] == 1
        assert metrics["max_concurrent_children"] == 1
        assert metrics["active_parents"] == 1
        assert metrics["active_children"] == 1
        assert metrics["total_relationships"] == 1

    async def test_multiple_children_metrics(self):
        """Test metrics with multiple children."""
        tracker = ChildRunTracker()
        parent_id = uuid4()
        
        # Register multiple children
        child_ids = [uuid4() for _ in range(3)]
        for child_id in child_ids:
            await tracker.register_child(parent_id, child_id)
        
        metrics = await tracker.get_metrics()
        
        assert metrics["registration_count"] == 3
        assert metrics["max_concurrent_children"] == 3
        assert metrics["active_parents"] == 1
        assert metrics["active_children"] == 3
        assert metrics["total_relationships"] == 3

    async def test_unregistration_metrics(self):
        """Test unregistration metrics tracking."""
        tracker = ChildRunTracker()
        parent_id = uuid4()
        child_id = uuid4()
        
        await tracker.register_child(parent_id, child_id)
        await tracker.unregister_child(parent_id, child_id)
        metrics = await tracker.get_metrics()
        
        assert metrics["registration_count"] == 1
        assert metrics["unregistration_count"] == 1
        assert metrics["active_parents"] == 0
        assert metrics["active_children"] == 0
        assert metrics["total_relationships"] == 0

    async def test_lookup_metrics(self):
        """Test lookup operation metrics."""
        tracker = ChildRunTracker()
        parent_id = uuid4()
        child_id = uuid4()
        
        await tracker.register_child(parent_id, child_id)
        
        # Test get_children lookup
        await tracker.get_children(parent_id)
        await tracker.get_parent(child_id)
        
        metrics = await tracker.get_metrics()
        assert metrics["lookup_count"] == 2

    async def test_tree_traversal_metrics(self):
        """Test tree traversal metrics."""
        tracker = ChildRunTracker()
        root_id = uuid4()
        
        # Create a tree: root -> child1 -> grandchild1
        child1_id = uuid4()
        grandchild1_id = uuid4()
        
        await tracker.register_child(root_id, child1_id)
        await tracker.register_child(child1_id, grandchild1_id)
        
        # Test tree traversal
        descendants = await tracker.get_all_descendants(root_id)
        
        metrics = await tracker.get_metrics()
        assert metrics["tree_traversal_count"] == 1
        assert len(descendants) == 2  # child1 + grandchild1

    async def test_depth_tracking_metrics(self):
        """Test depth tracking metrics."""
        tracker = ChildRunTracker()
        
        # Create a chain: root -> child1 -> child2 -> child3
        root_id = uuid4()
        child1_id = uuid4()
        child2_id = uuid4()
        child3_id = uuid4()
        
        await tracker.register_child(root_id, child1_id)
        await tracker.register_child(child1_id, child2_id)
        await tracker.register_child(child2_id, child3_id)
        
        # Get root for deepest child to update depth tracking
        await tracker.get_root_run(child3_id)
        
        metrics = await tracker.get_metrics()
        assert metrics["max_depth_seen"] == 3

    async def test_cleanup_metrics(self):
        """Test cleanup operation metrics."""
        tracker = ChildRunTracker()
        parent_id = uuid4()
        child_id = uuid4()
        
        await tracker.register_child(parent_id, child_id)
        await tracker.cleanup_run(child_id)
        
        metrics = await tracker.get_metrics()
        assert metrics["cleanup_count"] == 1
        assert metrics["active_children"] == 0

    async def test_reset_metrics(self):
        """Test metrics reset functionality."""
        tracker = ChildRunTracker()
        parent_id = uuid4()
        child_id = uuid4()
        
        # Perform some operations
        await tracker.register_child(parent_id, child_id)
        await tracker.get_children(parent_id)
        await tracker.get_all_descendants(parent_id)
        
        # Reset metrics
        await tracker.reset_metrics()
        metrics = await tracker.get_metrics()
        
        # All counters should be zero
        assert metrics["registration_count"] == 0
        assert metrics["unregistration_count"] == 0
        assert metrics["lookup_count"] == 0
        assert metrics["tree_traversal_count"] == 0
        assert metrics["cleanup_count"] == 0
        assert metrics["max_concurrent_children"] == 0
        assert metrics["max_depth_seen"] == 0

    async def test_concurrent_metrics_updates(self):
        """Test thread-safe metrics updates."""
        tracker = ChildRunTracker()
        parent_id = uuid4()
        
        # Concurrent registrations
        tasks = []
        for i in range(10):
            child_id = uuid4()
            tasks.append(tracker.register_child(parent_id, child_id))
        
        await asyncio.gather(*tasks)
        
        metrics = await tracker.get_metrics()
        assert metrics["registration_count"] == 10
        assert metrics["max_concurrent_children"] == 10


class TestChildTrackerMetricsInterceptor:
    """Tests for ChildTrackerMetricsInterceptor."""

    def test_interceptor_properties(self):
        """Test interceptor basic properties."""
        interceptor = ChildTrackerMetricsInterceptor()
        
        assert interceptor.name == "child_tracker_metrics"
        assert interceptor.priority == 45

    async def test_before_no_op(self):
        """Test before() method is no-op."""
        interceptor = ChildTrackerMetricsInterceptor()
        ctx = MagicMock()
        
        # Should not raise any errors
        await interceptor.before("test_stage", ctx)

    async def test_after_logs_metrics_for_child_run(self):
        """Test after() logs metrics for child runs."""
        interceptor = ChildTrackerMetricsInterceptor()
        
        # Create a mock context that's a child run
        ctx = MagicMock()
        ctx.pipeline_run_id = uuid4()
        ctx.is_child_run = True
        
        # Create a mock result
        result = MagicMock()
        
        # Mock the logger
        with pytest.MonkeyPatch().context() as m:
            mock_logger = MagicMock()
            m.setattr("logging.getLogger", lambda name: mock_logger)
            
            # Mock the tracker
            tracker = AsyncMock()
            tracker.get_metrics.return_value = {
                "registration_count": 5,
                "active_children": 2,
            }
            
            m.setattr("stageflow.pipeline.subpipeline.get_child_tracker", lambda: tracker)
            
            await interceptor.after("test_stage", result, ctx)
            
            # Should have logged metrics
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert call_args[0][0] == "ChildRunTracker metrics"
            
            # Check extra data contains metrics
            extra = call_args[1]["extra"]
            assert extra["component"] == "ChildRunTracker"
            assert extra["is_child_run"] is True
            assert extra["registration_count"] == 5
            assert extra["active_children"] == 2

    async def test_after_skips_non_child_runs(self):
        """Test after() skips metrics for non-child runs."""
        interceptor = ChildTrackerMetricsInterceptor()
        
        # Create a mock context that's NOT a child run
        ctx = MagicMock()
        ctx.pipeline_run_id = uuid4()
        # Explicitly set is_child_run to False
        ctx.is_child_run = False
        
        result = MagicMock()
        
        # Mock the logger
        with pytest.MonkeyPatch().context() as m:
            mock_logger = MagicMock()
            m.setattr("logging.getLogger", lambda name: mock_logger)
            
            await interceptor.after("test_stage", result, ctx)
            
            # Should not have logged anything
            mock_logger.info.assert_not_called()

    async def test_after_handles_gracefully_on_error(self):
        """Test after() handles errors gracefully."""
        interceptor = ChildTrackerMetricsInterceptor()
        
        ctx = MagicMock()
        ctx.pipeline_run_id = uuid4()
        ctx.is_child_run = True
        result = MagicMock()
        
        # Mock the logger
        with pytest.MonkeyPatch().context() as m:
            mock_logger = MagicMock()
            m.setattr("logging.getLogger", lambda name: mock_logger)
            
            # Mock get_child_tracker to raise an error
            def raise_error():
                raise Exception("Tracker error")
            m.setattr("stageflow.pipeline.subpipeline.get_child_tracker", raise_error)
            
            # Should not raise an exception
            await interceptor.after("test_stage", result, ctx)
            
            # Should have logged a warning
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args
            assert "Failed to log ChildRunTracker metrics" in str(warning_call)


class TestChildTrackerMetricsIntegration:
    """Integration tests for ChildRunTracker metrics."""

    async def test_global_tracker_functions(self):
        """Test global tracker management functions."""
        # Clear any existing tracker
        clear_child_tracker()
        
        # Test getting/setting tracker
        tracker1 = get_child_tracker()
        assert isinstance(tracker1, ChildRunTracker)
        
        custom_tracker = ChildRunTracker()
        set_child_tracker(custom_tracker)
        
        tracker2 = get_child_tracker()
        assert tracker2 is custom_tracker
        
        # Clear and verify new instance
        clear_child_tracker()
        tracker3 = get_child_tracker()
        assert tracker3 is not custom_tracker
        assert isinstance(tracker3, ChildRunTracker)

    def test_included_in_default_interceptors(self):
        """Test ChildTrackerMetricsInterceptor is in default interceptors."""
        interceptors = get_default_interceptors()
        
        # Find the child tracker metrics interceptor
        child_tracker_interceptor = None
        for interceptor in interceptors:
            if hasattr(interceptor, 'name') and interceptor.name == 'child_tracker_metrics':
                child_tracker_interceptor = interceptor
                break
        
        assert child_tracker_interceptor is not None
        assert isinstance(child_tracker_interceptor, ChildTrackerMetricsInterceptor)
        assert child_tracker_interceptor.priority == 45

    async def test_end_to_end_metrics_flow(self):
        """Test end-to-end metrics flow."""
        # Set up a fresh tracker
        tracker = ChildRunTracker()
        set_child_tracker(tracker)
        
        # Simulate some subpipeline activity
        parent_id = uuid4()
        child_id = uuid4()
        
        await tracker.register_child(parent_id, child_id)
        await tracker.get_children(parent_id)
        await tracker.get_parent(child_id)
        
        # Check metrics
        metrics = await tracker.get_metrics()
        assert metrics["registration_count"] == 1
        assert metrics["lookup_count"] == 2
        assert metrics["active_children"] == 1
        
        # Cleanup
        await tracker.unregister_child(parent_id, child_id)
        await tracker.cleanup_run(child_id)
        
        final_metrics = await tracker.get_metrics()
        assert final_metrics["unregistration_count"] == 1
        assert final_metrics["cleanup_count"] == 1
        assert final_metrics["active_children"] == 0
