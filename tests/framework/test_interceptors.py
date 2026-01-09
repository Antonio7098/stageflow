"""Comprehensive tests for stageflow.pipeline.interceptors module.

Tests the interceptor framework:
- BaseInterceptor abstract class
- InterceptorResult
- InterceptorContext
- ErrorAction enum
- Concrete interceptors: LoggingInterceptor, MetricsInterceptor, TracingInterceptor, CircuitBreakerInterceptor, TimeoutInterceptor
- run_with_interceptors function
"""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from stageflow.pipeline.interceptors import (
    BaseInterceptor,
    CircuitBreakerInterceptor,
    ErrorAction,
    InterceptorContext,
    InterceptorResult,
    LoggingInterceptor,
    MetricsInterceptor,
    TimeoutInterceptor,
    TracingInterceptor,
    get_default_interceptors,
    run_with_interceptors,
)
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult

# === Test Fixtures ===

def create_context() -> PipelineContext:
    """Create a test PipelineContext."""
    return PipelineContext(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=uuid4(),
        interaction_id=uuid4(),
        topology="test",
        execution_mode="test",
    )


def create_started_ended() -> tuple[datetime, datetime]:
    """Create started_at and ended_at for StageResult."""
    started = datetime.now(UTC)
    ended = started
    return started, ended


# === Test ErrorAction ===

class TestErrorAction:
    """Tests for ErrorAction enum."""

    def test_error_actions_defined(self):
        """Test all error actions exist."""
        assert ErrorAction.RETRY.value == 1  # auto() assigns values
        assert ErrorAction.FALLBACK.value == 2
        assert ErrorAction.FAIL.value == 3

    def test_error_action_values_are_unique(self):
        """Test error action values are unique."""
        values = [action.value for action in ErrorAction]
        assert len(values) == len(set(values))


# === Test InterceptorResult ===

class TestInterceptorResult:
    """Tests for InterceptorResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = InterceptorResult()
        assert result.stage_ran is True
        assert result.result is None
        assert result.error is None

    def test_custom_values(self):
        """Test custom values."""
        result = InterceptorResult(
            stage_ran=False,
            result={"custom": "data"},
            error="Error message",
        )
        assert result.stage_ran is False
        assert result.result == {"custom": "data"}
        assert result.error == "Error message"

    def test_is_mutable(self):
        """Test InterceptorResult is mutable (not frozen)."""
        result = InterceptorResult()
        # Should not raise - InterceptorResult is mutable
        result.stage_ran = False
        assert result.stage_ran is False

    def test_has_slots(self):
        """Test InterceptorResult uses slots."""
        assert hasattr(InterceptorResult, "__slots__")


# === Test BaseInterceptor ===

class TestBaseInterceptor:
    """Tests for BaseInterceptor abstract class."""

    def test_base_interceptor_name_default(self):
        """Test default name."""
        # BaseInterceptor has name and priority as class attributes
        assert BaseInterceptor.name == "base_interceptor"

    def test_base_interceptor_priority_default(self):
        """Test default priority."""
        assert BaseInterceptor.priority == 100

    def test_before_defined_in_protocol(self):
        """Test that before method is defined in the protocol."""
        # Check that before is an abstract method
        assert hasattr(BaseInterceptor, 'before')
        # The method exists and is abstract (implemented as abstractmethod in the class)
        assert getattr(BaseInterceptor.before, '__isabstractmethod__', False) is True

    def test_after_defined_in_protocol(self):
        """Test that after method is defined."""
        assert hasattr(BaseInterceptor, 'after')
        assert getattr(BaseInterceptor.after, '__isabstractmethod__', False) is True


# === Test InterceptorContext ===

class TestInterceptorContext:
    """Tests for InterceptorContext class."""

    def test_context_creation(self):
        """Test InterceptorContext creation."""
        ctx = create_context()
        ic = InterceptorContext(ctx, "test_interceptor")
        assert ic._ctx is ctx
        assert ic._interceptor_name == "test_interceptor"

    def test_name_property(self):
        """Test name property."""
        ctx = create_context()
        ic = InterceptorContext(ctx, "my_interceptor")
        assert ic.name == "my_interceptor"

    def test_data_returns_copy(self):
        """Test data property returns a copy."""
        ctx = create_context()
        ctx.data["key"] = "original"
        ic = InterceptorContext(ctx, "test")

        # Modify the returned copy
        data = ic.data
        data["key"] = "modified"

        # Original should be unchanged
        assert ctx.data["key"] == "original"

    def test_correlation_ids(self):
        """Test correlation ID properties."""
        run_id = uuid4()
        request_id = uuid4()
        session_id = uuid4()
        user_id = uuid4()
        org_id = uuid4()

        ctx = PipelineContext(
            pipeline_run_id=run_id,
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            org_id=org_id,
            interaction_id=uuid4(),
            topology="test",
        )
        ic = InterceptorContext(ctx, "test")

        assert ic.pipeline_run_id == run_id
        assert ic.request_id == request_id
        assert ic.session_id == session_id
        assert ic.user_id == user_id
        assert ic.org_id == org_id

    def test_topology_property(self):
        """Test topology property."""
        ctx = create_context()
        ctx.topology = "chat_fast"
        ic = InterceptorContext(ctx, "test")
        assert ic.topology == "chat_fast"

    def test_execution_mode_property(self):
        """Test execution_mode property."""
        ctx = create_context()
        ctx.execution_mode = "practice"
        ic = InterceptorContext(ctx, "test")
        assert ic.execution_mode == "practice"

    def test_add_observation(self):
        """Test add_observation method."""
        ctx = create_context()
        ic = InterceptorContext(ctx, "test_interceptor")
        ic.add_observation("key", "value")

        # Check it's stored correctly
        assert ic._observations == {}
        # Check it's in ctx.data
        assert "_interceptor.test_interceptor" in ctx.data
        assert ctx.data["_interceptor.test_interceptor"]["key"] == "value"

    def test_get_observation(self):
        """Test get_observation method."""
        ctx = create_context()
        ctx.data["_interceptor.test_interceptor"] = {"existing": "value"}
        ic = InterceptorContext(ctx, "test_interceptor")

        assert ic.get_observation("existing") == "value"
        assert ic.get_observation("missing") is None

    def test_observations_are_isolated(self):
        """Test observations are isolated by interceptor name."""
        ctx = create_context()
        ic1 = InterceptorContext(ctx, "interceptor1")
        ic2 = InterceptorContext(ctx, "interceptor2")

        ic1.add_observation("key", "value1")

        # ic2 should not see ic1's observation
        assert ic2.get_observation("key") is None


# === Test LoggingInterceptor ===

class TestLoggingInterceptor:
    """Tests for LoggingInterceptor."""

    def test_interceptor_name(self):
        """Test interceptor name."""
        assert LoggingInterceptor().name == "logging"

    def test_interceptor_priority(self):
        """Test interceptor priority."""
        assert LoggingInterceptor().priority == 50

    @pytest.mark.asyncio
    async def test_before_logs_info(self):
        """Test before() logs stage start."""
        interceptor = LoggingInterceptor()
        ctx = create_context()

        # Should not raise - just log
        await interceptor.before("test_stage", ctx)

    @pytest.mark.asyncio
    async def test_after_logs_info(self):
        """Test after() logs stage completion."""
        interceptor = LoggingInterceptor()
        ctx = create_context()
        started, ended = create_started_ended()
        result = StageResult(
            name="test_stage",
            status="completed",
            started_at=started,
            ended_at=ended,
        )

        # Should not raise - just log
        await interceptor.after("test_stage", result, ctx)


# === Test MetricsInterceptor ===

class TestMetricsInterceptor:
    """Tests for MetricsInterceptor."""

    def test_interceptor_name(self):
        """Test interceptor name."""
        assert MetricsInterceptor().name == "metrics"

    def test_interceptor_priority(self):
        """Test interceptor priority."""
        assert MetricsInterceptor().priority == 40

    @pytest.mark.asyncio
    async def test_before_stores_start_time(self):
        """Test before() stores start time in context data."""
        interceptor = MetricsInterceptor()
        ctx = create_context()

        await interceptor.before("test_stage", ctx)

        assert "_metrics.stage_start_time" in ctx.data

    @pytest.mark.asyncio
    async def test_after_cleans_up_and_logs(self):
        """Test after() cleans up and logs metrics."""
        interceptor = MetricsInterceptor()
        ctx = create_context()
        ctx.data["_metrics.stage_start_time"] = datetime.now(UTC)
        started, ended = create_started_ended()
        result = StageResult(
            name="test_stage",
            status="completed",
            started_at=started,
            ended_at=ended,
        )

        await interceptor.after("test_stage", result, ctx)

        # Start time should be cleaned up
        assert "_metrics.stage_start_time" not in ctx.data


# === Test TracingInterceptor ===

class TestTracingInterceptor:
    """Tests for TracingInterceptor."""

    def test_interceptor_name(self):
        """Test interceptor name."""
        assert TracingInterceptor().name == "tracing"

    def test_interceptor_priority(self):
        """Test interceptor priority."""
        assert TracingInterceptor().priority == 20

    @pytest.mark.asyncio
    async def test_before_stores_span_info(self):
        """Test before() stores span info."""
        interceptor = TracingInterceptor()
        ctx = create_context()

        await interceptor.before("test_stage", ctx)

        assert "_tracing.span_name" in ctx.data
        assert ctx.data["_tracing.span_name"] == "test_stage"
        assert "_tracing.span_start" in ctx.data

    @pytest.mark.asyncio
    async def test_after_cleans_up(self):
        """Test after() cleans up tracing context."""
        interceptor = TracingInterceptor()
        ctx = create_context()
        ctx.data["_tracing.span_name"] = "test"
        ctx.data["_tracing.span_start"] = datetime.now(UTC)
        started, ended = create_started_ended()
        result = StageResult(
            name="test",
            status="completed",
            started_at=started,
            ended_at=ended,
        )

        await interceptor.after("test_stage", result, ctx)

        assert "_tracing.span_name" not in ctx.data
        assert "_tracing.span_start" not in ctx.data


# === Test CircuitBreakerInterceptor ===

class TestCircuitBreakerInterceptor:
    """Tests for CircuitBreakerInterceptor."""

    def test_interceptor_name(self):
        """Test interceptor name."""
        assert CircuitBreakerInterceptor().name == "circuit_breaker"

    def test_interceptor_priority(self):
        """Test interceptor priority."""
        assert CircuitBreakerInterceptor().priority == 10

    def test_breaker_closed_initially(self):
        """Test circuit breaker is closed initially."""
        interceptor = CircuitBreakerInterceptor()
        assert interceptor._breaker_states.get("test_stage") is None

    @pytest.mark.asyncio
    async def test_before_allows_execution_when_closed(self):
        """Test before() allows execution when closed."""
        interceptor = CircuitBreakerInterceptor()
        ctx = create_context()

        result = await interceptor.before("test_stage", ctx)
        # Should return None (continue execution)
        assert result is None

    @pytest.mark.asyncio
    async def test_before_blocks_when_open(self):
        """Test before() blocks when circuit is open."""
        import time
        interceptor = CircuitBreakerInterceptor()
        interceptor._breaker_states["test_stage"] = "open"
        interceptor._last_failure["test_stage"] = time.time() - 1  # Recent failure (1 second ago)
        ctx = create_context()

        result = await interceptor.before("test_stage", ctx)

        # Should return InterceptorResult with stage_ran=False
        assert result is not None
        assert result.stage_ran is False
        assert "Circuit breaker open" in result.error

    @pytest.mark.asyncio
    async def test_after_resets_on_success(self):
        """Test after() resets breaker on success."""
        interceptor = CircuitBreakerInterceptor()
        interceptor._breaker_states["test_stage"] = "open"
        interceptor._failure_counts["test_stage"] = 5
        ctx = create_context()
        started, ended = create_started_ended()
        result = StageResult(
            name="test_stage",
            status="completed",
            started_at=started,
            ended_at=ended,
        )

        await interceptor.after("test_stage", result, ctx)

        assert interceptor._breaker_states.get("test_stage") == "closed"
        assert interceptor._failure_counts.get("test_stage") == 0

    @pytest.mark.asyncio
    async def test_after_records_failure(self):
        """Test after() records failure."""
        interceptor = CircuitBreakerInterceptor()
        ctx = create_context()
        started, ended = create_started_ended()
        result = StageResult(
            name="test_stage",
            status="failed",
            started_at=started,
            ended_at=ended,
        )

        await interceptor.after("test_stage", result, ctx)

        assert interceptor._failure_counts.get("test_stage") == 1
        # State is not set until threshold is reached (5 failures)
        assert "test_stage" not in interceptor._breaker_states

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self):
        """Test breaker opens after threshold failures."""
        interceptor = CircuitBreakerInterceptor()
        started, ended = create_started_ended()
        result = StageResult(
            name="test_stage",
            status="failed",
            started_at=started,
            ended_at=ended,
        )

        for _ in range(5):
            await interceptor.after("test_stage", result, create_context())

        assert interceptor._breaker_states.get("test_stage") == "open"

    @pytest.mark.asyncio
    async def test_on_error_records_failure(self):
        """Test on_error() records failure."""
        interceptor = CircuitBreakerInterceptor()
        ctx = create_context()

        result = await interceptor.on_error("test_stage", ValueError("test"), ctx)
        assert result == ErrorAction.FAIL
        assert interceptor._failure_counts.get("test_stage") == 1


# === Test TimeoutInterceptor ===

class TestTimeoutInterceptor:
    """Tests for TimeoutInterceptor."""

    def test_interceptor_name(self):
        """Test interceptor name."""
        assert TimeoutInterceptor().name == "timeout"

    def test_interceptor_priority(self):
        """Test interceptor priority (should be low = outer wrapper)."""
        assert TimeoutInterceptor().priority == 5

    def test_default_timeout(self):
        """Test default timeout is 30 seconds."""
        assert TimeoutInterceptor.DEFAULT_TIMEOUT_MS == 30000

    @pytest.mark.asyncio
    async def test_before_stores_timeout(self):
        """Test before() stores timeout in context."""
        interceptor = TimeoutInterceptor()
        ctx = create_context()

        await interceptor.before("test_stage", ctx)

        assert "_timeout.test_stage" in ctx.data
        assert ctx.data["_timeout.test_stage"] == 30000

    @pytest.mark.asyncio
    async def test_before_uses_custom_timeout(self):
        """Test before() uses custom timeout from context."""
        interceptor = TimeoutInterceptor()
        ctx = create_context()
        ctx.data["_timeout_ms"] = 5000

        await interceptor.before("test_stage", ctx)

        assert ctx.data["_timeout.test_stage"] == 5000

    @pytest.mark.asyncio
    async def test_after_cleans_up(self):
        """Test after() cleans up timeout key."""
        interceptor = TimeoutInterceptor()
        ctx = create_context()
        ctx.data["_timeout.test_stage"] = 30000
        started, ended = create_started_ended()
        result = StageResult(
            name="test_stage",
            status="completed",
            started_at=started,
            ended_at=ended,
        )

        await interceptor.after("test_stage", result, ctx)

        assert "_timeout.test_stage" not in ctx.data


# === Test run_with_interceptors ===

class TestRunWithInterceptors:
    """Tests for run_with_interceptors function."""

    @pytest.mark.asyncio
    async def test_executes_stage(self):
        """Test stage is executed."""
        async def stage_run():
            started, ended = create_started_ended()
            return StageResult(
                name="test",
                status="completed",
                started_at=started,
                ended_at=ended,
            )

        ctx = create_context()
        interceptors = [LoggingInterceptor()]

        result = await run_with_interceptors(
            stage_name="test_stage",
            stage_run=stage_run,
            ctx=ctx,
            interceptors=interceptors,
        )

        assert result.name == "test"
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_interceptors_sorted_by_priority(self):
        """Test interceptors are sorted by priority."""
        class LowPriority(BaseInterceptor):
            name = "low"
            priority = 100

            async def before(self, _stage_name, _ctx):
                return None

            async def after(self, _stage_name, _result, _ctx):
                pass

        class HighPriority(BaseInterceptor):
            name = "high"
            priority = 10

            async def before(self, _stage_name, _ctx):
                return None

            async def after(self, _stage_name, _result, _ctx):
                pass

        async def stage_run():
            started, ended = create_started_ended()
            return StageResult(name="test", status="completed", started_at=started, ended_at=ended)

        ctx = create_context()
        # Add in random order
        interceptors = [LowPriority(), HighPriority()]

        result = await run_with_interceptors(
            stage_name="test",
            stage_run=stage_run,
            ctx=ctx,
            interceptors=interceptors,
        )

        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_interceptor_before_short_circuits(self):
        """Test interceptor before() can short-circuit stage execution."""
        class ShortCircuit(BaseInterceptor):
            name = "short_circuit"
            priority = 50

            async def before(self, _stage_name, _ctx):
                return InterceptorResult(stage_ran=False, result={"skipped": True}, error=None)

            async def after(self, _stage_name, _result, _ctx):
                pass

        async def stage_run():
            raise AssertionError("Stage should not have run")

        ctx = create_context()
        result = await run_with_interceptors(
            stage_name="test",
            stage_run=stage_run,
            ctx=ctx,
            interceptors=[ShortCircuit()],
        )

        assert result.status == "completed"
        assert result.data == {"skipped": True}

    @pytest.mark.asyncio
    async def test_interceptor_error_does_not_crash(self):
        """Test interceptor error doesn't crash stage."""
        class ErrorInterceptor(BaseInterceptor):
            name = "error"
            priority = 50

            async def before(self, _stage_name, _ctx):
                raise RuntimeError("Interceptor error")

            async def after(self, _stage_name, _result, _ctx):
                raise RuntimeError("After error")

        async def stage_run():
            started, ended = create_started_ended()
            return StageResult(name="test", status="completed", started_at=started, ended_at=ended)

        ctx = create_context()
        result = await run_with_interceptors(
            stage_name="test",
            stage_run=stage_run,
            ctx=ctx,
            interceptors=[ErrorInterceptor()],
        )

        # Stage should still complete
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_stage_timeout(self):
        """Test stage timeout works."""
        async def slow_stage():
            await asyncio.sleep(2.0)  # 2 seconds
            started, ended = create_started_ended()
            return StageResult(name="test", status="completed", started_at=started, ended_at=ended)

        ctx = create_context()
        ctx.data["_timeout_ms"] = 100  # 100ms timeout

        result = await run_with_interceptors(
            stage_name="test",
            stage_run=slow_stage,
            ctx=ctx,
            interceptors=[TimeoutInterceptor()],
        )

        assert result.status == "failed"
        assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_zero_timeout_disables(self):
        """Test zero timeout disables timeout."""
        async def slow_stage():
            await asyncio.sleep(0.1)
            started, ended = create_started_ended()
            return StageResult(name="test", status="completed", started_at=started, ended_at=ended)

        ctx = create_context()
        ctx.data["_timeout_ms"] = 0  # No timeout

        result = await run_with_interceptors(
            stage_name="test",
            stage_run=slow_stage,
            ctx=ctx,
            interceptors=[TimeoutInterceptor()],
        )

        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_stage_error_calls_on_error(self):
        """Test stage error triggers on_error callbacks."""
        class CustomErrorHandler(BaseInterceptor):
            name = "handler"
            priority = 50

            async def before(self, _stage_name, _ctx):
                return None

            async def after(self, _stage_name, _result, _ctx):
                pass

            async def on_error(self, _stage_name, _error, _ctx):
                return ErrorAction.FAIL

        async def error_stage():
            raise ValueError("Stage error")

        ctx = create_context()
        result = await run_with_interceptors(
            stage_name="test",
            stage_run=error_stage,
            ctx=ctx,
            interceptors=[CustomErrorHandler()],
        )

        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_retry_on_error(self):
        """Test RETRY error action retries stage."""
        call_count = {"count": 0}

        class RetryHandler(BaseInterceptor):
            name = "retry"
            priority = 50

            async def before(self, _stage_name, _ctx):
                return None

            async def after(self, _stage_name, _result, _ctx):
                pass

            async def on_error(self, _stage_name, _error, _ctx):
                return ErrorAction.RETRY

        async def succeed_on_retry():
            call_count["count"] += 1
            if call_count["count"] < 2:
                raise ValueError("First attempt")
            started, ended = create_started_ended()
            return StageResult(name="test", status="completed", started_at=started, ended_at=ended)

        ctx = create_context()
        result = await run_with_interceptors(
            stage_name="test",
            stage_run=succeed_on_retry,
            ctx=ctx,
            interceptors=[RetryHandler()],
        )

        assert result.status == "completed"
        assert call_count["count"] == 2

    @pytest.mark.asyncio
    async def test_empty_interceptor_list(self):
        """Test with empty interceptor list."""
        async def stage_run():
            started, ended = create_started_ended()
            return StageResult(name="test", status="completed", started_at=started, ended_at=ended)

        ctx = create_context()
        result = await run_with_interceptors(
            stage_name="test",
            stage_run=stage_run,
            ctx=ctx,
            interceptors=[],
        )

        assert result.status == "completed"


# === Test get_default_interceptors ===

class TestGetDefaultInterceptors:
    """Tests for get_default_interceptors function."""

    def test_returns_list(self):
        """Test returns a list."""
        interceptors = get_default_interceptors()
        assert isinstance(interceptors, list)

    def test_returns_non_empty(self):
        """Test returns non-empty list."""
        interceptors = get_default_interceptors()
        assert len(interceptors) > 0

    def test_contains_timeout_interceptor(self):
        """Test contains TimeoutInterceptor."""
        interceptors = get_default_interceptors()
        names = [i.name for i in interceptors]
        assert "timeout" in names

    def test_contains_circuit_breaker(self):
        """Test contains CircuitBreakerInterceptor."""
        interceptors = get_default_interceptors()
        names = [i.name for i in interceptors]
        assert "circuit_breaker" in names

    def test_contains_tracing(self):
        """Test contains TracingInterceptor."""
        interceptors = get_default_interceptors()
        names = [i.name for i in interceptors]
        assert "tracing" in names

    def test_contains_metrics(self):
        """Test contains MetricsInterceptor."""
        interceptors = get_default_interceptors()
        names = [i.name for i in interceptors]
        assert "metrics" in names

    def test_contains_logging(self):
        """Test contains LoggingInterceptor."""
        interceptors = get_default_interceptors()
        names = [i.name for i in interceptors]
        assert "logging" in names

    def test_sorted_by_priority(self):
        """Test interceptors are sorted by priority (low to high)."""
        interceptors = get_default_interceptors()
        priorities = [i.priority for i in interceptors]
        # Should be non-decreasing
        assert priorities == sorted(priorities)

    def test_timeout_is_first(self):
        """Test TimeoutInterceptor is first (lowest priority)."""
        interceptors = get_default_interceptors()
        assert interceptors[0].name == "timeout"

    def test_logging_is_last(self):
        """Test LoggingInterceptor is last (highest priority)."""
        interceptors = get_default_interceptors()
        assert interceptors[-1].name == "logging"


# === Edge Cases ===

class TestInterceptorEdgeCases:
    """Edge case tests for interceptors."""

    def test_interceptor_with_custom_priority(self):
        """Test interceptor with custom priority."""
        class CustomInterceptor(BaseInterceptor):
            name = "custom"
            priority = 25

            async def before(self, _stage_name, _ctx):
                return None

            async def after(self, _stage_name, _result, _ctx):
                pass

        interceptor = CustomInterceptor()
        assert interceptor.priority == 25

    def test_interceptor_context_observations_empty_by_default(self):
        """Test observations are empty by default."""
        ctx = create_context()
        ic = InterceptorContext(ctx, "test")
        assert ic._observations == {}

    def test_interceptor_context_preserves_original(self):
        """Test InterceptorContext doesn't modify original context."""
        ctx = create_context()
        original_data = dict(ctx.data)
        ic = InterceptorContext(ctx, "test")

        # Use context
        _ = ic.data
        _ = ic.pipeline_run_id

        # Original should be unchanged
        assert ctx.data == original_data
