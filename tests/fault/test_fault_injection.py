"""Tests for fault injection framework."""

from __future__ import annotations

import asyncio

import pytest

from tests.fault.injection import (
    CircuitBreakerTestHelper,
    FaultConfig,
    FaultInjector,
    FaultType,
    inject_fault,
)


class TestFaultInjector:
    """Tests for the FaultInjector class."""

    @pytest.mark.asyncio
    async def test_timeout_fault_raises_timeout_error(self) -> None:
        """Timeout fault raises asyncio.TimeoutError."""
        config = FaultConfig(
            fault_type=FaultType.TIMEOUT,
            duration_ms=10,  # Short timeout for test
            message="Test timeout",
        )
        injector = FaultInjector(config)

        with pytest.raises(asyncio.TimeoutError):
            await injector.maybe_fault()

        assert injector.call_count == 1

    @pytest.mark.asyncio
    async def test_error_fault_raises_runtime_error(self) -> None:
        """Error fault raises RuntimeError."""
        config = FaultConfig(
            fault_type=FaultType.ERROR,
            message="Test error",
        )
        injector = FaultInjector(config)

        with pytest.raises(RuntimeError) as exc_info:
            await injector.maybe_fault()

        assert "Test error" in str(exc_info.value)
        assert injector.fault_count == 1

    @pytest.mark.asyncio
    async def test_slow_fault_delays_execution(self) -> None:
        """Slow fault delays execution."""
        config = FaultConfig(
            fault_type=FaultType.SLOW,
            duration_ms=50,
            slow_factor=1.0,
        )
        injector = FaultInjector(config)

        start = asyncio.get_event_loop().time()
        await injector.maybe_fault()
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed >= 0.05  # At least 50ms

    @pytest.mark.asyncio
    async def test_intermittent_fault_sometimes_fails(self) -> None:
        """Intermittent fault fails based on failure_rate."""
        config = FaultConfig(
            fault_type=FaultType.INTERMITTENT,
            failure_rate=1.0,  # Always fail
            message="Intermittent failure",
        )
        injector = FaultInjector(config)

        with pytest.raises(RuntimeError):
            await injector.maybe_fault()

    @pytest.mark.asyncio
    async def test_intermittent_fault_sometimes_succeeds(self) -> None:
        """Intermittent fault succeeds based on failure_rate."""
        config = FaultConfig(
            fault_type=FaultType.INTERMITTENT,
            failure_rate=0.0,  # Never fail
            message="Intermittent failure",
        )
        injector = FaultInjector(config)

        # Should not raise
        await injector.maybe_fault()
        assert injector.fault_count == 0


class TestInjectFaultContextManager:
    """Tests for the inject_fault context manager."""

    def test_inject_fault_creates_injector(self) -> None:
        """inject_fault creates a FaultInjector."""
        with inject_fault("llm", FaultType.ERROR) as injector:
            assert injector.provider_name == "llm"
            assert injector.config.fault_type == FaultType.ERROR

    def test_inject_fault_accepts_custom_message(self) -> None:
        """inject_fault accepts custom error message."""
        with inject_fault("stt", FaultType.ERROR, message="Custom error") as injector:
            assert injector.config.message == "Custom error"

    def test_inject_fault_accepts_duration(self) -> None:
        """inject_fault accepts duration_ms parameter."""
        with inject_fault("tts", FaultType.TIMEOUT, duration_ms=1000) as injector:
            assert injector.config.duration_ms == 1000


class TestCircuitBreakerHelper:
    """Tests for the CircuitBreakerTestHelper."""

    def test_circuit_opens_after_threshold_failures(self) -> None:
        """Circuit opens after reaching failure threshold."""
        helper = CircuitBreakerTestHelper(failure_threshold=3)

        assert not helper.is_open
        helper.record_failure()
        assert not helper.is_open
        helper.record_failure()
        assert not helper.is_open
        helper.record_failure()
        assert helper.is_open

    def test_success_resets_failure_count(self) -> None:
        """Success resets failure count and closes circuit."""
        helper = CircuitBreakerTestHelper(failure_threshold=3)

        helper.record_failure()
        helper.record_failure()
        helper.record_success()

        assert helper.failure_count == 0
        assert not helper.is_open

    def test_reset_clears_state(self) -> None:
        """Reset clears all state."""
        helper = CircuitBreakerTestHelper(failure_threshold=2)

        helper.record_failure()
        helper.record_failure()
        assert helper.is_open

        helper.reset()
        assert not helper.is_open
        assert helper.failure_count == 0
