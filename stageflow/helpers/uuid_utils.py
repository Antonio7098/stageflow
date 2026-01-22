"""UUID telemetry helpers for collision detection and instrumentation.

Provides a lightweight monitor that keeps a sliding window of recently
observed UUIDs so high-level components (ToolExecutor, PipelineRunner)
can detect suspicious reuse and emit observability events.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

try:
    import uuid6
    HAS_UUID7 = True
except ImportError:
    HAS_UUID7 = False

logger = logging.getLogger("stageflow.helpers.uuid")

UuidEventListener = Callable[["UuidEvent"], None]


@dataclass(frozen=True)
class UuidEvent:
    """UUID telemetry data captured by the monitor."""

    value: UUID
    collision: bool
    category: str
    observed_at: datetime
    skew_ms: float | None = None


def generate_uuid7() -> UUID:
    """Generate a UUIDv7 (time-ordered) if available, falling back to UUIDv4.

    UUIDv7 provides k-sortability which is beneficial for database indexing
    and log correlation.
    """
    if HAS_UUID7:
        return uuid6.uuid7()
    return uuid4()


class ClockSkewDetector:
    """Detects if UUIDv7 timestamps deviate significantly from system clock."""

    def __init__(self, max_skew_ms: float = 5000.0) -> None:
        self.max_skew_ms = max_skew_ms

    def check(self, uid: UUID) -> float | None:
        """Check skew for a UUIDv7. Returns skew in ms if significant, else None."""
        if not HAS_UUID7 or uid.version != 7:
            return None

        # Extract timestamp from UUIDv7 (top 48 bits)
        # uuid7 timestamp is milliseconds since epoch
        ts_ms = uid.int >> 80
        uuid_time = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
        system_time = datetime.now(UTC)

        skew = abs((system_time - uuid_time).total_seconds() * 1000)
        if skew > self.max_skew_ms:
            return skew
        return None


class UuidCollisionMonitor:
    """Sliding-window UUID collision detector with optional listeners.

    Parameters
    ----------
    ttl_seconds:
        How long to retain UUIDs in the sliding window.
    max_entries:
        Hard upper bound on the tracking window to protect memory usage.
    category:
        Logical namespace ("pipeline", "tool", etc.) attached to events.
    check_skew:
        Whether to check for clock skew on UUIDv7s.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = 300.0,
        max_entries: int = 50_000,
        category: str = "default",
        listeners: Iterable[UuidEventListener] | None = None,
        check_skew: bool = False,
    ) -> None:
        self._ttl = timedelta(seconds=max(ttl_seconds, 1.0))
        self._max_entries = max(1, max_entries)
        self._category = category
        self._entries: deque[tuple[datetime, str]] = deque()
        self._index: set[str] = set()
        self._listeners: list[UuidEventListener] = list(listeners or [])
        self._skew_detector = ClockSkewDetector() if check_skew else None

    @property
    def category(self) -> str:
        return self._category

    def add_listener(self, listener: UuidEventListener) -> None:
        """Register a listener that receives :class:`UuidEvent` records."""

        self._listeners.append(listener)

    def observe(self, value: UUID) -> bool:
        """Record a UUID and return True if it is a collision within the window."""

        now = datetime.now(UTC)
        key = str(value)
        collision = key in self._index
        self._entries.append((now, key))
        self._index.add(key)
        self._trim(now)

        skew_ms = None
        if self._skew_detector:
            skew_ms = self._skew_detector.check(value)
            if skew_ms is not None:
                logger.warning(
                    f"Clock skew detected for UUID {value}: {skew_ms:.1f}ms",
                    extra={"uuid": str(value), "skew_ms": skew_ms}
                )

        event = UuidEvent(
            value=value,
            collision=collision,
            category=self._category,
            observed_at=now,
            skew_ms=skew_ms,
        )
        for listener in self._listeners:
            listener(event)
        return collision

    def _trim(self, now: datetime) -> None:
        cutoff = now - self._ttl
        while self._entries and (self._entries[0][0] < cutoff or len(self._entries) > self._max_entries):
            _, old = self._entries.popleft()
            if old in self._index:
                self._index.remove(old)


__all__ = [
    "UuidCollisionMonitor",
    "UuidEvent",
    "UuidEventListener",
    "generate_uuid7",
    "ClockSkewDetector",
]
