"""Tests for retry interceptor."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from stageflow.pipeline.retry import (
    BackoffStrategy,
    JitterStrategy,
    RateLimitError,
    RetryInterceptor,
    ServiceUnavailableError,
    TransientError,
)
from stageflow.pipeline.interceptors import ErrorAction


class TestBackoffStrategy:
    """Tests for BackoffStrategy enum."""

    def test_all_strategies_defined(self):
        """Verify all backoff strategies are defined."""
        strategies = [
            BackoffStrategy.EXPONENTIAL,
            BackoffStrategy.LINEAR,
            BackoffStrategy.CONSTANT,
        ]
        assert len(strategies) == 3


class TestJitterStrategy:
    """Tests for JitterStrategy enum."""

    def test_all_strategies_defined(self):
        """Verify all jitter strategies are defined."""
        strategies = [
            JitterStrategy.NONE,
            JitterStrategy.FULL,
            JitterStrategy.EQUAL,
            JitterStrategy.DECORRELATED,
        ]
        assert len(strategies) == 4


class TestRetryInterceptor:
    """Tests for RetryInterceptor."""

    def test_initialization(self):
        """Test interceptor initialization with defaults."""
        interceptor = RetryInterceptor()
        
        assert interceptor.max_attempts == 3
        assert interceptor.base_delay_ms == 1000
        assert interceptor.max_delay_ms == 30000
        assert interceptor.backoff_strategy == BackoffStrategy.EXPONENTIAL
        assert interceptor.jitter_strategy == JitterStrategy.FULL

    def test_custom_initialization(self):
        """Test interceptor initialization with custom values."""
        interceptor = RetryInterceptor(
            max_attempts=5,
            base_delay_ms=500,
            max_delay_ms=10000,
            backoff_strategy=BackoffStrategy.LINEAR,
            jitter_strategy=JitterStrategy.NONE,
        )
        
        assert interceptor.max_attempts == 5
        assert interceptor.base_delay_ms == 500
        assert interceptor.backoff_strategy == BackoffStrategy.LINEAR

    def test_exponential_delay_calculation(self):
        """Test exponential backoff delay calculation."""
        interceptor = RetryInterceptor(
            base_delay_ms=1000,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_strategy=JitterStrategy.NONE,
        )
        
        # attempt 0: 1000 * 2^0 = 1000
        assert interceptor._calculate_delay("test", 0) == 1000
        # attempt 1: 1000 * 2^1 = 2000
        assert interceptor._calculate_delay("test", 1) == 2000
        # attempt 2: 1000 * 2^2 = 4000
        assert interceptor._calculate_delay("test", 2) == 4000

    def test_linear_delay_calculation(self):
        """Test linear backoff delay calculation."""
        interceptor = RetryInterceptor(
            base_delay_ms=1000,
            backoff_strategy=BackoffStrategy.LINEAR,
            jitter_strategy=JitterStrategy.NONE,
        )
        
        # attempt 0: 1000 * 1 = 1000
        assert interceptor._calculate_delay("test", 0) == 1000
        # attempt 1: 1000 * 2 = 2000
        assert interceptor._calculate_delay("test", 1) == 2000
        # attempt 2: 1000 * 3 = 3000
        assert interceptor._calculate_delay("test", 2) == 3000

    def test_constant_delay_calculation(self):
        """Test constant backoff delay calculation."""
        interceptor = RetryInterceptor(
            base_delay_ms=1000,
            backoff_strategy=BackoffStrategy.CONSTANT,
            jitter_strategy=JitterStrategy.NONE,
        )
        
        # All attempts should have same delay
        assert interceptor._calculate_delay("test", 0) == 1000
        assert interceptor._calculate_delay("test", 1) == 1000
        assert interceptor._calculate_delay("test", 2) == 1000

    def test_max_delay_cap(self):
        """Test that delay is capped at max_delay_ms."""
        interceptor = RetryInterceptor(
            base_delay_ms=10000,
            max_delay_ms=15000,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_strategy=JitterStrategy.NONE,
        )
        
        # attempt 2: 10000 * 4 = 40000, but capped at 15000
        assert interceptor._calculate_delay("test", 2) == 15000

    def test_jitter_full_range(self):
        """Test full jitter produces values in expected range."""
        interceptor = RetryInterceptor(
            base_delay_ms=1000,
            backoff_strategy=BackoffStrategy.CONSTANT,
            jitter_strategy=JitterStrategy.FULL,
        )
        
        # Run multiple times to verify range
        delays = [interceptor._calculate_delay("test", 0) for _ in range(100)]
        
        # All values should be in [0, 1000]
        assert all(0 <= d <= 1000 for d in delays)
        # Should have some variation (not all same)
        assert len(set(delays)) > 1

    def test_jitter_equal_range(self):
        """Test equal jitter produces values in expected range."""
        interceptor = RetryInterceptor(
            base_delay_ms=1000,
            backoff_strategy=BackoffStrategy.CONSTANT,
            jitter_strategy=JitterStrategy.EQUAL,
        )
        
        # Run multiple times to verify range
        delays = [interceptor._calculate_delay("test", 0) for _ in range(100)]
        
        # All values should be in [500, 1000] (half fixed, half random)
        assert all(500 <= d <= 1000 for d in delays)

    @pytest.mark.asyncio
    async def test_before_initializes_retry_state(self):
        """Test that before() initializes retry state."""
        interceptor = RetryInterceptor()
        
        ctx = MagicMock()
        ctx.data = {}
        
        await interceptor.before("test_stage", ctx)
        
        assert "_retry.test_stage" in ctx.data
        assert ctx.data["_retry.test_stage"]["attempt"] == 0

    @pytest.mark.asyncio
    async def test_on_error_retryable_error(self):
        """Test on_error returns RETRY for retryable errors."""
        interceptor = RetryInterceptor(
            max_attempts=3,
            base_delay_ms=10,  # Short delay for test
            jitter_strategy=JitterStrategy.NONE,
        )
        
        ctx = MagicMock()
        ctx.data = {"_retry.test_stage": {"attempt": 0}}
        ctx.event_sink = MagicMock()
        ctx.event_sink.try_emit = MagicMock()
        
        error = TimeoutError("Connection timed out")
        
        action = await interceptor.on_error("test_stage", error, ctx)
        
        assert action == ErrorAction.RETRY
        assert ctx.data["_retry.test_stage"]["attempt"] == 1

    @pytest.mark.asyncio
    async def test_on_error_non_retryable_error(self):
        """Test on_error returns FAIL for non-retryable errors."""
        interceptor = RetryInterceptor()
        
        ctx = MagicMock()
        ctx.data = {"_retry.test_stage": {"attempt": 0}}
        
        error = ValueError("Invalid input")  # Not in retryable_errors
        
        action = await interceptor.on_error("test_stage", error, ctx)
        
        assert action == ErrorAction.FAIL

    @pytest.mark.asyncio
    async def test_on_error_exhausted_retries(self):
        """Test on_error returns FAIL when retries exhausted."""
        interceptor = RetryInterceptor(max_attempts=3)
        
        ctx = MagicMock()
        ctx.data = {"_retry.test_stage": {"attempt": 2}}  # Already tried 2 times
        ctx.event_sink = MagicMock()
        ctx.event_sink.try_emit = MagicMock()
        
        error = TimeoutError("Connection timed out")
        
        action = await interceptor.on_error("test_stage", error, ctx)
        
        assert action == ErrorAction.FAIL

    @pytest.mark.asyncio
    async def test_custom_retryable_errors(self):
        """Test custom retryable error types."""
        interceptor = RetryInterceptor(
            max_attempts=3,
            base_delay_ms=10,
            retryable_errors=(RateLimitError, ServiceUnavailableError),
            jitter_strategy=JitterStrategy.NONE,
        )
        
        ctx = MagicMock()
        ctx.data = {"_retry.test_stage": {"attempt": 0}}
        ctx.event_sink = MagicMock()
        ctx.event_sink.try_emit = MagicMock()
        
        # RateLimitError should be retryable
        error = RateLimitError("Rate limit exceeded", retry_after=60)
        action = await interceptor.on_error("test_stage", error, ctx)
        assert action == ErrorAction.RETRY
        
        # Reset state
        ctx.data = {"_retry.test_stage": {"attempt": 0}}
        
        # TimeoutError should NOT be retryable (not in custom list)
        error = TimeoutError("Timeout")
        action = await interceptor.on_error("test_stage", error, ctx)
        assert action == ErrorAction.FAIL


class TestTransientErrors:
    """Tests for transient error types."""

    def test_rate_limit_error(self):
        """Test RateLimitError attributes."""
        error = RateLimitError("Rate limit exceeded", retry_after=60)
        
        assert str(error) == "Rate limit exceeded"
        assert error.retry_after == 60

    def test_service_unavailable_error(self):
        """Test ServiceUnavailableError."""
        error = ServiceUnavailableError("Service temporarily unavailable")
        
        assert isinstance(error, TransientError)
        assert str(error) == "Service temporarily unavailable"
