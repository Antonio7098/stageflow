"""Fault injection framework for testing graceful degradation.

This module provides context managers and utilities for injecting
faults into providers and stages to test error handling.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FaultType(StrEnum):
    """Types of faults that can be injected."""

    TIMEOUT = "timeout"
    ERROR = "error"
    SLOW = "slow"
    INTERMITTENT = "intermittent"
    EMPTY_RESPONSE = "empty_response"
    INVALID_RESPONSE = "invalid_response"


@dataclass
class FaultConfig:
    """Configuration for a fault injection."""

    fault_type: FaultType
    duration_ms: int = 5000
    message: str = "Injected fault"
    failure_rate: float = 0.5  # For intermittent faults
    slow_factor: float = 10.0  # Multiplier for slow responses
    extra: dict[str, Any] = field(default_factory=dict)


class FaultInjector:
    """Base class for fault injectors."""

    def __init__(self, config: FaultConfig) -> None:
        self.config = config
        self._original: Any = None
        self._call_count = 0
        self._fault_count = 0

    async def maybe_fault(self) -> None:
        """Raise or delay based on fault configuration."""
        self._call_count += 1

        if self.config.fault_type == FaultType.TIMEOUT:
            await asyncio.sleep(self.config.duration_ms / 1000)
            raise TimeoutError(self.config.message)

        elif self.config.fault_type == FaultType.ERROR:
            self._fault_count += 1
            raise RuntimeError(self.config.message)

        elif self.config.fault_type == FaultType.SLOW:
            await asyncio.sleep(self.config.duration_ms / 1000 * self.config.slow_factor)

        elif self.config.fault_type == FaultType.INTERMITTENT:
            import random
            if random.random() < self.config.failure_rate:
                self._fault_count += 1
                raise RuntimeError(self.config.message)

    @property
    def call_count(self) -> int:
        """Number of times the faulty operation was called."""
        return self._call_count

    @property
    def fault_count(self) -> int:
        """Number of faults that were actually triggered."""
        return self._fault_count


class ProviderFaultInjector(FaultInjector):
    """Fault injector for provider calls (LLM, STT, TTS, etc)."""

    def __init__(self, provider_name: str, config: FaultConfig) -> None:
        super().__init__(config)
        self.provider_name = provider_name

    def create_faulty_handler(self, original: Callable) -> Callable:
        """Wrap an original handler to inject faults."""

        async def faulty_handler(*args: Any, **kwargs: Any) -> Any:
            await self.maybe_fault()
            return await original(*args, **kwargs)

        return faulty_handler


@contextmanager
def inject_fault(
    target: str,
    fault_type: FaultType,
    *,
    duration_ms: int = 5000,
    message: str = "Injected fault",
    **kwargs: Any,
) -> Generator[FaultInjector, None, None]:
    """Context manager to inject a fault into a target.

    Args:
        target: Target to inject fault into (e.g., "llm", "stt")
        fault_type: Type of fault to inject
        duration_ms: Duration for timeout/slow faults
        message: Error message for error faults
        **kwargs: Additional fault configuration

    Yields:
        FaultInjector instance for inspection

    Example:
        with inject_fault("llm", FaultType.TIMEOUT, duration_ms=5000):
            result = await pipeline.run(ctx)
            assert result.status == "failed"
    """
    config = FaultConfig(
        fault_type=fault_type,
        duration_ms=duration_ms,
        message=message,
        **kwargs,
    )
    injector = ProviderFaultInjector(target, config)

    # For now, just yield the injector - actual patching would depend on
    # the specific provider implementation
    yield injector


@asynccontextmanager
async def inject_fault_async(
    target: str,
    fault_type: FaultType,
    *,
    duration_ms: int = 5000,
    message: str = "Injected fault",
    **kwargs: Any,
) -> AsyncGenerator[FaultInjector, None]:
    """Async context manager version of inject_fault."""
    config = FaultConfig(
        fault_type=fault_type,
        duration_ms=duration_ms,
        message=message,
        **kwargs,
    )
    injector = ProviderFaultInjector(target, config)
    yield injector


class CircuitBreakerTestHelper:
    """Helper for testing circuit breaker behavior."""

    def __init__(self, failure_threshold: int = 5) -> None:
        self.failure_threshold = failure_threshold
        self.failure_count = 0
        self.is_open = False

    def record_failure(self) -> None:
        """Record a failure and check if circuit should open."""
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.is_open = True

    def record_success(self) -> None:
        """Record a success."""
        self.failure_count = 0
        self.is_open = False

    def reset(self) -> None:
        """Reset the circuit breaker state."""
        self.failure_count = 0
        self.is_open = False


__all__ = [
    "FaultType",
    "FaultConfig",
    "FaultInjector",
    "ProviderFaultInjector",
    "inject_fault",
    "inject_fault_async",
    "CircuitBreakerTestHelper",
]
