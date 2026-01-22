"""Runtime memory tracking utilities for pipelines and stages.

Provides a lightweight tracker plus a decorator that can wrap sync/async
functions to emit memory samples without taking a hard dependency on psutil.
Uses the standard library `tracemalloc` module so it works anywhere Python does.
"""

from __future__ import annotations

import functools
import inspect
import tracemalloc
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, TypeVar

T = TypeVar("T")
Func = Callable[..., T]
AsyncFunc = Callable[..., Awaitable[T]]
Listener = Callable[["MemorySample"], None]


@dataclass(frozen=True)
class MemorySample:
    """Single memory observation captured by a tracker."""

    timestamp: datetime
    current_kb: int
    peak_kb: int
    label: str | None = None


@dataclass
class MemoryTracker:
    """Simple helper around `tracemalloc` to capture memory growth."""

    auto_start: bool = True
    listeners: list[Listener] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.samples: list[MemorySample] = []
        self._active = False
        if self.auto_start:
            self.start()

    def start(self) -> None:
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        self._active = True

    def stop(self) -> None:
        self._active = False

    def observe(self, *, label: str | None = None) -> MemorySample:
        if not self._active:
            raise RuntimeError("MemoryTracker is not active; call start() first")
        current, peak = tracemalloc.get_traced_memory()
        sample = MemorySample(
            timestamp=datetime.now(UTC),
            current_kb=current // 1024,
            peak_kb=peak // 1024,
            label=label,
        )
        self.samples.append(sample)
        for listener in self.listeners:
            listener(sample)
        return sample

    def extend_listeners(self, extra: Iterable[Listener]) -> None:
        self.listeners.extend(extra)


class SampleEmitter(Protocol):
    def emit_sample(self, sample: MemorySample) -> None: ...  # pragma: no cover


def track_memory(
    *,
    label: str | None = None,
    tracker: MemoryTracker | None = None,
) -> Callable[[Func | AsyncFunc], Func | AsyncFunc]:
    """Decorator that records memory usage before/after the wrapped function."""

    def decorator(func: Func | AsyncFunc):
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any):
                local_tracker = tracker or MemoryTracker(auto_start=True)
                local_tracker.observe(label=f"{label or func.__name__}:start")
                try:
                    return await func(*args, **kwargs)
                finally:
                    local_tracker.observe(label=f"{label or func.__name__}:end")

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any):
            local_tracker = tracker or MemoryTracker(auto_start=True)
            local_tracker.observe(label=f"{label or func.__name__}:start")
            try:
                return func(*args, **kwargs)
            finally:
                local_tracker.observe(label=f"{label or func.__name__}:end")

        return sync_wrapper

    return decorator


__all__ = [
    "MemorySample",
    "MemoryTracker",
    "track_memory",
]
