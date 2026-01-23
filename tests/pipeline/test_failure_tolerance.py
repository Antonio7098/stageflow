"""Tests for pipeline failure tolerance utilities."""

import asyncio
import pytest

from stageflow.pipeline.failure_tolerance import (
    BackpressureConfig,
    BackpressureMonitor,
    ConditionalDependency,
    FailureCollector,
    FailureMode,
    FailureRecord,
    FailureSummary,
)


class TestFailureMode:
    """Tests for FailureMode enum."""

    def test_fail_fast_is_default(self):
        """Verify FAIL_FAST is a valid mode."""
        assert FailureMode.FAIL_FAST.name == "FAIL_FAST"

    def test_all_modes_defined(self):
        """Verify all failure modes are defined."""
        modes = [FailureMode.FAIL_FAST, FailureMode.CONTINUE_ON_FAILURE, FailureMode.BEST_EFFORT]
        assert len(modes) == 3


class TestFailureCollector:
    """Tests for FailureCollector."""

    def test_record_failure(self):
        """Test recording a failure."""
        collector = FailureCollector(mode=FailureMode.CONTINUE_ON_FAILURE)
        
        collector.record_failure(
            stage="test_stage",
            error="Test error",
            recoverable=False,
        )
        
        assert collector.has_failures
        assert "test_stage" in collector.failed_stages

    def test_record_completion(self):
        """Test recording a completion."""
        collector = FailureCollector()
        
        collector.record_completion("stage_a")
        collector.record_completion("stage_b")
        
        summary = collector.get_summary(total_stages=2, partial_results={})
        assert summary.completed_stages == 2

    def test_should_continue_fail_fast(self):
        """Test FAIL_FAST mode stops on any failure."""
        collector = FailureCollector(mode=FailureMode.FAIL_FAST)
        
        # Before failure, should continue
        assert collector.should_continue("stage_b", set())
        
        # Record failure
        collector.record_failure("stage_a", "Error")
        
        # After failure, should not continue
        assert not collector.should_continue("stage_b", set())

    def test_should_continue_on_failure(self):
        """Test CONTINUE_ON_FAILURE mode skips dependent stages."""
        collector = FailureCollector(mode=FailureMode.CONTINUE_ON_FAILURE)
        
        # Record failure for stage_a
        collector.record_failure("stage_a", "Error")
        
        # Unrelated stage should continue
        assert collector.should_continue("stage_c", {"stage_b"})
        
        # Dependent stage should not continue
        assert not collector.should_continue("stage_b", {"stage_a"})

    def test_should_continue_best_effort(self):
        """Test BEST_EFFORT mode always continues."""
        collector = FailureCollector(mode=FailureMode.BEST_EFFORT)
        
        # Record failures
        collector.record_failure("stage_a", "Error")
        collector.record_failure("stage_b", "Error")
        
        # Should always continue
        assert collector.should_continue("stage_c", {"stage_a", "stage_b"})

    def test_get_summary(self):
        """Test failure summary generation."""
        collector = FailureCollector()
        
        collector.record_failure("stage_a", "Error 1")
        collector.record_completion("stage_b")
        collector.record_completion("stage_c")
        
        summary = collector.get_summary(
            total_stages=3,
            partial_results={"stage_b": {}, "stage_c": {}},
        )
        
        assert summary.total_stages == 3
        assert summary.completed_stages == 2
        assert summary.failed_stages == 1
        assert summary.has_failures
        assert len(summary.failures) == 1

    def test_success_rate(self):
        """Test success rate calculation."""
        collector = FailureCollector()
        
        collector.record_completion("stage_a")
        collector.record_completion("stage_b")
        collector.record_failure("stage_c", "Error")
        
        summary = collector.get_summary(total_stages=3, partial_results={})
        assert summary.success_rate == pytest.approx(2/3)


class TestBackpressureMonitor:
    """Tests for BackpressureMonitor."""

    def test_initial_state(self):
        """Test initial monitor state."""
        config = BackpressureConfig(max_active_stages=10)
        monitor = BackpressureMonitor(config)
        
        assert monitor.utilization == 0.0
        assert not monitor.is_overloaded

    @pytest.mark.asyncio
    async def test_acquire_release(self):
        """Test acquire and release flow."""
        config = BackpressureConfig(max_active_stages=2)
        monitor = BackpressureMonitor(config)
        
        # Acquire first slot
        assert await monitor.acquire()
        assert monitor._active_count == 1
        
        # Release
        monitor.release(latency_ms=100)
        assert monitor._active_count == 0

    @pytest.mark.asyncio
    async def test_utilization_tracking(self):
        """Test utilization calculation."""
        config = BackpressureConfig(max_active_stages=4)
        monitor = BackpressureMonitor(config)
        
        # Acquire 2 of 4 slots
        await monitor.acquire()
        await monitor.acquire()
        
        assert monitor.utilization == 0.5

    def test_overload_detection(self):
        """Test overload detection based on watermark."""
        config = BackpressureConfig(
            max_active_stages=10,
            high_watermark=0.8,
        )
        monitor = BackpressureMonitor(config)
        
        # Manually set active count to test
        monitor._active_count = 9  # 90% utilization
        
        assert monitor.is_overloaded

    def test_metrics(self):
        """Test metrics reporting."""
        monitor = BackpressureMonitor()
        
        metrics = monitor.get_metrics()
        
        assert "active_count" in metrics
        assert "utilization" in metrics
        assert "is_overloaded" in metrics


class TestConditionalDependency:
    """Tests for ConditionalDependency."""

    def test_simple_key_check_true(self):
        """Test simple key check that evaluates to true."""
        dep = ConditionalDependency(
            stage="stage_b",
            predicate="stage_a:should_run",
        )
        
        class MockOutput:
            data = {"should_run": True}
        
        outputs = {"stage_a": MockOutput()}
        
        assert dep.evaluate(outputs) is True

    def test_simple_key_check_false(self):
        """Test simple key check that evaluates to false."""
        dep = ConditionalDependency(
            stage="stage_b",
            predicate="stage_a:should_run",
            skip_on_false=True,
        )
        
        class MockOutput:
            data = {"should_run": False}
        
        outputs = {"stage_a": MockOutput()}
        
        assert dep.evaluate(outputs) is False

    def test_missing_stage_defaults_to_true(self):
        """Test that missing stage defaults to executing."""
        dep = ConditionalDependency(
            stage="stage_b",
            predicate="missing_stage:key",
        )
        
        outputs = {}
        
        assert dep.evaluate(outputs) is True

    def test_evaluation_error_defaults_to_true(self):
        """Test that evaluation errors default to executing."""
        dep = ConditionalDependency(
            stage="stage_b",
            predicate="invalid:predicate:format",
        )
        
        outputs = {"stage_a": {"data": {}}}
        
        # Should not raise, should return True
        result = dep.evaluate(outputs)
        assert result is True
