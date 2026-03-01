"""Analytics export adapters for pipeline observability.

This module provides exporters for pipeline analytics data:
- JSON file exporter for local analysis
- Console exporter for debugging
- Buffered exporter with batch writes
- Protocol for custom exporters (Snowflake, BigQuery, etc.)

Usage:
    from stageflow.helpers import AnalyticsExporter, JSONFileExporter, BufferedExporter

    # Create an exporter
    exporter = JSONFileExporter("pipeline_events.jsonl")

    # Buffer events for batch writes
    buffered = BufferedExporter(exporter, batch_size=100, flush_interval_seconds=10)

    # Export events
    await buffered.export(AnalyticsEvent(
        event_type="stage.completed",
        stage_name="llm",
        duration_ms=150,
        data={"tokens": 500},
    ))
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

# Type alias for overflow callback
OverflowCallback = Callable[[int, int], None]  # (dropped_count, buffer_size) -> None


@dataclass
class AnalyticsEvent:
    """An analytics event for export.

    Attributes:
        event_type: Type of event (e.g., "stage.completed", "pipeline.started").
        timestamp: When the event occurred.
        data: Event-specific data.
        pipeline_run_id: Pipeline run identifier.
        stage_name: Stage name (if applicable).
        duration_ms: Duration in milliseconds (if applicable).
        metadata: Additional metadata.
    """

    event_type: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = field(default_factory=dict)
    pipeline_run_id: UUID | None = None
    stage_name: str | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }

        if self.pipeline_run_id:
            result["pipeline_run_id"] = str(self.pipeline_run_id)
        if self.stage_name:
            result["stage_name"] = self.stage_name
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        if self.metadata:
            result["metadata"] = self.metadata

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalyticsEvent:
        """Create from dictionary."""
        return cls(
            event_type=data["event_type"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data["timestamp"], str) else data["timestamp"],
            data=data.get("data", {}),
            pipeline_run_id=UUID(data["pipeline_run_id"]) if data.get("pipeline_run_id") else None,
            stage_name=data.get("stage_name"),
            duration_ms=data.get("duration_ms"),
            metadata=data.get("metadata", {}),
        )


class AnalyticsExporter(Protocol):
    """Protocol for analytics exporters.

    Implement this to create custom exporters for your analytics platform.
    """

    async def export(self, event: AnalyticsEvent) -> None:
        """Export a single event."""
        ...

    async def export_batch(self, events: list[AnalyticsEvent]) -> None:
        """Export multiple events."""
        ...

    async def flush(self) -> None:
        """Flush any buffered events."""
        ...

    async def close(self) -> None:
        """Close the exporter and clean up resources."""
        ...


class JSONFileExporter:
    """Exports analytics events to a JSON Lines file.

    Each event is written as a single JSON line for easy parsing.
    Useful for local analysis or feeding into BI tools.

    Example:
        exporter = JSONFileExporter("events.jsonl")
        await exporter.export(event)
        await exporter.close()
    """

    def __init__(
        self,
        file_path: str | Path,
        *,
        append: bool = True,
    ) -> None:
        """Initialize exporter.

        Args:
            file_path: Path to output file.
            append: If True, append to existing file. If False, overwrite.
        """
        self._path = Path(file_path)
        self._append = append
        self._file: Any | None = None
        self._lock = asyncio.Lock()
        self._event_count = 0

    async def _ensure_open(self) -> None:
        """Ensure file is open."""
        if self._file is None:
            mode = "a" if self._append else "w"
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self._path, mode)  # noqa: SIM115

    async def export(self, event: AnalyticsEvent) -> None:
        """Export a single event."""
        async with self._lock:
            await self._ensure_open()
            line = json.dumps(event.to_dict(), default=str)
            self._file.write(line + "\n")
            self._event_count += 1

    async def export_batch(self, events: list[AnalyticsEvent]) -> None:
        """Export multiple events."""
        async with self._lock:
            await self._ensure_open()
            for event in events:
                line = json.dumps(event.to_dict(), default=str)
                self._file.write(line + "\n")
            self._event_count += len(events)

    async def flush(self) -> None:
        """Flush the file buffer."""
        async with self._lock:
            if self._file:
                self._file.flush()

    async def close(self) -> None:
        """Close the file."""
        async with self._lock:
            if self._file:
                self._file.close()
                self._file = None

    @property
    def event_count(self) -> int:
        """Get number of events exported."""
        return self._event_count


class ConsoleExporter:
    """Exports analytics events to console for debugging.

    Useful during development to see events in real-time.

    Example:
        exporter = ConsoleExporter(colorize=True)
        await exporter.export(event)
    """

    def __init__(
        self,
        *,
        colorize: bool = True,
        verbose: bool = False,
    ) -> None:
        """Initialize exporter.

        Args:
            colorize: Use ANSI colors in output.
            verbose: Show full event data.
        """
        self._colorize = colorize
        self._verbose = verbose
        self._event_count = 0

    def _format_event(self, event: AnalyticsEvent) -> str:
        """Format event for display."""
        # Color codes
        if self._colorize:
            reset = "\033[0m"
            if "error" in event.event_type or "fail" in event.event_type:
                color = "\033[91m"  # Red
            elif "complete" in event.event_type or "success" in event.event_type:
                color = "\033[92m"  # Green
            elif "start" in event.event_type:
                color = "\033[94m"  # Blue
            else:
                color = "\033[96m"  # Cyan
        else:
            reset = color = ""

        # Format timestamp
        ts = event.timestamp.strftime("%H:%M:%S.%f")[:-3]

        # Build output
        parts = [f"{color}[{ts}] {event.event_type}{reset}"]

        if event.stage_name:
            parts.append(f"  stage: {event.stage_name}")
        if event.duration_ms is not None:
            parts.append(f"  duration: {event.duration_ms:.1f}ms")

        if self._verbose and event.data:
            parts.append(f"  data: {json.dumps(event.data, default=str)}")

        return "\n".join(parts)

    async def export(self, event: AnalyticsEvent) -> None:
        """Export a single event."""
        print(self._format_event(event))
        self._event_count += 1

    async def export_batch(self, events: list[AnalyticsEvent]) -> None:
        """Export multiple events."""
        for event in events:
            await self.export(event)

    async def flush(self) -> None:
        """No-op for console."""
        pass

    async def close(self) -> None:
        """No-op for console."""
        pass

    @property
    def event_count(self) -> int:
        """Get number of events exported."""
        return self._event_count


class BufferedExporter:
    """Wraps an exporter with buffering for batch writes.

    Accumulates events and writes them in batches for better performance.
    Supports time-based flushing for low-volume scenarios.
    Supports optional overflow callback for alerting on buffer pressure.

    Example:
        base = JSONFileExporter("events.jsonl")
        buffered = BufferedExporter(base, batch_size=100, flush_interval_seconds=10)

        await buffered.export(event)  # Buffered
        await buffered.flush()  # Force write

        # With overflow callback
        def on_overflow(dropped, buffer_size):
            print(f"Warning: dropped {dropped} events, buffer at {buffer_size}")

        buffered = BufferedExporter(base, on_overflow=on_overflow)
    """

    def __init__(
        self,
        exporter: AnalyticsExporter | None = None,
        *,
        sink: AnalyticsExporter | None = None,
        batch_size: int = 100,
        flush_interval_seconds: float = 10.0,
        flush_interval: float | None = None,
        max_buffer_size: int = 10000,
        on_overflow: OverflowCallback | None = None,
        high_water_mark: float = 0.8,
    ) -> None:
        """Initialize buffered exporter.

        Args:
            exporter: Underlying exporter to write to.
            sink: Backward-compatible alias for exporter.
            batch_size: Number of events to batch before writing.
            flush_interval_seconds: Maximum time before flush.
            flush_interval: Backward-compatible alias for flush_interval_seconds.
            max_buffer_size: Maximum events to buffer (drops oldest if exceeded).
            on_overflow: Optional callback when events are dropped due to overflow.
            high_water_mark: Buffer fill ratio (0-1) to trigger high water warning.
        """
        resolved_exporter = exporter if exporter is not None else sink
        if resolved_exporter is None:
            raise TypeError("BufferedExporter requires 'exporter' (or legacy alias 'sink').")
        self._exporter = resolved_exporter
        self._batch_size = batch_size
        self._flush_interval = (
            flush_interval if flush_interval is not None else flush_interval_seconds
        )
        self._max_buffer = max_buffer_size
        self._buffer: list[AnalyticsEvent] = []
        self._lock = asyncio.Lock()
        self._last_flush = datetime.now(UTC)
        self._flush_task: asyncio.Task[None] | None = None
        self._closed = False
        self._dropped_count = 0
        self._on_overflow = on_overflow
        self._high_water_mark = high_water_mark
        self._high_water_warned = False

    async def _start_flush_timer(self) -> None:
        """Start background flush timer."""
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._flush_loop())

    async def _flush_loop(self) -> None:
        """Background flush loop."""
        while not self._closed:
            await asyncio.sleep(self._flush_interval)
            await self.flush()

    async def export(self, event: AnalyticsEvent) -> None:
        """Export a single event (buffered)."""
        async with self._lock:
            # Start flush timer if needed
            if self._flush_task is None and not self._closed:
                await self._start_flush_timer()

            # Drop oldest if buffer is full
            if len(self._buffer) >= self._max_buffer:
                self._buffer.pop(0)
                self._dropped_count += 1
                # Notify via callback
                if self._on_overflow is not None:
                    import contextlib
                    with contextlib.suppress(Exception):
                        self._on_overflow(self._dropped_count, len(self._buffer))

            self._buffer.append(event)

            # Check high water mark
            fill_ratio = len(self._buffer) / self._max_buffer
            if fill_ratio >= self._high_water_mark and not self._high_water_warned:
                self._high_water_warned = True
                if self._on_overflow is not None:
                    import contextlib
                    with contextlib.suppress(Exception):
                        # Signal high water with negative dropped_count as convention
                        self._on_overflow(-1, len(self._buffer))
            elif fill_ratio < self._high_water_mark * 0.5:
                # Reset warning when buffer drains significantly
                self._high_water_warned = False

            # Flush if batch size reached
            if len(self._buffer) >= self._batch_size:
                await self._do_flush()

    async def export_batch(self, events: list[AnalyticsEvent]) -> None:
        """Export multiple events (buffered)."""
        for event in events:
            await self.export(event)

    async def _do_flush(self) -> None:
        """Perform actual flush (must be called with lock held)."""
        if not self._buffer:
            return

        events_to_write = self._buffer.copy()
        self._buffer.clear()
        self._last_flush = datetime.now(UTC)

        # Release lock during write
        await self._exporter.export_batch(events_to_write)

    async def flush(self) -> None:
        """Flush buffered events."""
        async with self._lock:
            await self._do_flush()

    async def close(self) -> None:
        """Close the exporter."""
        self._closed = True

        if self._flush_task:
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task

        await self.flush()
        await self._exporter.close()

    @property
    def buffer_size(self) -> int:
        """Current buffer size."""
        return len(self._buffer)

    @property
    def dropped_count(self) -> int:
        """Number of events dropped due to buffer overflow."""
        return self._dropped_count

    @property
    def stats(self) -> dict[str, Any]:
        """Get exporter statistics."""
        return {
            "buffer_size": len(self._buffer),
            "max_buffer_size": self._max_buffer,
            "dropped_count": self._dropped_count,
            "fill_ratio": len(self._buffer) / self._max_buffer if self._max_buffer > 0 else 0,
            "high_water_warned": self._high_water_warned,
        }


class CompositeExporter:
    """Exports to multiple destinations.

    Example:
        exporter = CompositeExporter([
            ConsoleExporter(),
            JSONFileExporter("events.jsonl"),
        ])
        await exporter.export(event)  # Written to both
    """

    def __init__(self, exporters: list[AnalyticsExporter]) -> None:
        """Initialize with list of exporters."""
        self._exporters = exporters

    async def export(self, event: AnalyticsEvent) -> None:
        """Export to all destinations."""
        await asyncio.gather(*[e.export(event) for e in self._exporters])

    async def export_batch(self, events: list[AnalyticsEvent]) -> None:
        """Export batch to all destinations."""
        await asyncio.gather(*[e.export_batch(events) for e in self._exporters])

    async def flush(self) -> None:
        """Flush all exporters."""
        await asyncio.gather(*[e.flush() for e in self._exporters])

    async def close(self) -> None:
        """Close all exporters."""
        await asyncio.gather(*[e.close() for e in self._exporters])


class AnalyticsSink:
    """EventSink adapter that exports events as analytics.

    Bridges stageflow's EventSink interface with AnalyticsExporter.

    Example:
        exporter = JSONFileExporter("events.jsonl")
        sink = AnalyticsSink(exporter)

        # Use as event sink
        ctx.event_sink = sink
    """

    def __init__(
        self,
        exporter: AnalyticsExporter,
        *,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        """Initialize sink.

        Args:
            exporter: Exporter to write to.
            include_patterns: Event type patterns to include (default: all).
            exclude_patterns: Event type patterns to exclude.
        """
        self._exporter = exporter
        self._include = include_patterns
        self._exclude = exclude_patterns or []

    def _should_export(self, event_type: str) -> bool:
        """Check if event should be exported."""
        # Check excludes first
        for pattern in self._exclude:
            if pattern in event_type:
                return False

        # If includes specified, check them
        if self._include:
            return any(pattern in event_type for pattern in self._include)

        return True

    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        """Emit an event asynchronously."""
        if not self._should_export(type):
            return

        event = AnalyticsEvent(
            event_type=type,
            data=data or {},
            pipeline_run_id=data.get("pipeline_run_id") if data else None,
            stage_name=data.get("stage") if data else None,
            duration_ms=data.get("duration_ms") if data else None,
        )
        await self._exporter.export(event)

    def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        """Emit an event synchronously (fire-and-forget)."""
        if not self._should_export(type):
            return

        event = AnalyticsEvent(
            event_type=type,
            data=data or {},
            pipeline_run_id=data.get("pipeline_run_id") if data else None,
            stage_name=data.get("stage") if data else None,
            duration_ms=data.get("duration_ms") if data else None,
        )
        # Schedule async export
        asyncio.create_task(self._exporter.export(event))


__all__ = [
    "AnalyticsEvent",
    "AnalyticsExporter",
    "AnalyticsSink",
    "BufferedExporter",
    "CompositeExporter",
    "ConsoleExporter",
    "JSONFileExporter",
]
