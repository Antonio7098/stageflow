"""Streaming primitives for audio and real-time pipelines.

This module provides utilities for handling streaming data:
- Chunk queues with backpressure
- Audio chunk management
- Streaming buffers for buffering/debuffering
- Backpressure monitoring

Usage:
    from stageflow.helpers import ChunkQueue, AudioChunk, BackpressureMonitor

    # Create a chunk queue with backpressure
    queue = ChunkQueue(max_size=100)

    # Producer
    async def producer():
        chunk = AudioChunk(data=audio_bytes, sample_rate=16000)
        await queue.put(chunk)

    # Consumer
    async def consumer():
        async for chunk in queue:
            process(chunk.data)
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, AsyncIterator, Generic, TypeVar

# Type alias for event emitter callback
EventEmitter = Callable[[str, dict[str, Any]], None]


class AudioFormat(Enum):
    """Supported audio formats."""

    PCM_16 = "pcm_16"
    PCM_24 = "pcm_24"
    PCM_32 = "pcm_32"
    FLOAT_32 = "float_32"
    MP3 = "mp3"
    OGG_OPUS = "ogg_opus"
    WAV = "wav"
    WEBM = "webm"


@dataclass(frozen=True)
class StreamConfig:
    """Configuration for streaming operations.

    Attributes:
        chunk_size: Default chunk size in bytes.
        sample_rate: Audio sample rate in Hz.
        channels: Number of audio channels.
        format: Audio format.
        buffer_duration_ms: Target buffer duration in milliseconds.
    """

    chunk_size: int = 4096
    sample_rate: int = 16000
    channels: int = 1
    format: AudioFormat = AudioFormat.PCM_16
    buffer_duration_ms: int = 100


@dataclass
class AudioChunk:
    """A chunk of audio data.

    Attributes:
        data: Raw audio bytes.
        sample_rate: Sample rate in Hz.
        channels: Number of channels.
        format: Audio format.
        timestamp_ms: Timestamp in milliseconds from stream start.
        sequence: Sequence number for ordering.
        is_final: Whether this is the last chunk.
        metadata: Additional metadata.
    """

    data: bytes
    sample_rate: int = 16000
    channels: int = 1
    format: AudioFormat = AudioFormat.PCM_16
    timestamp_ms: float = 0.0
    sequence: int = 0
    is_final: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        """Calculate chunk duration in milliseconds."""
        bytes_per_sample = 2 if self.format == AudioFormat.PCM_16 else 4
        samples = len(self.data) / (bytes_per_sample * self.channels)
        return (samples / self.sample_rate) * 1000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (data is base64 encoded)."""
        return {
            "data": base64.b64encode(self.data).decode("ascii"),
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "format": self.format.value,
            "timestamp_ms": self.timestamp_ms,
            "sequence": self.sequence,
            "is_final": self.is_final,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AudioChunk:
        """Create from dictionary."""
        return cls(
            data=base64.b64decode(data["data"]),
            sample_rate=data.get("sample_rate", 16000),
            channels=data.get("channels", 1),
            format=AudioFormat(data.get("format", "pcm_16")),
            timestamp_ms=data.get("timestamp_ms", 0.0),
            sequence=data.get("sequence", 0),
            is_final=data.get("is_final", False),
            metadata=data.get("metadata", {}),
        )


T = TypeVar("T")


@dataclass
class BackpressureStats:
    """Statistics about backpressure events.

    Attributes:
        total_items: Total items processed.
        dropped_items: Items dropped due to backpressure.
        blocked_puts: Times producer was blocked waiting.
        max_queue_size: Maximum queue size observed.
        total_blocked_ms: Total time spent blocked.
    """

    total_items: int = 0
    dropped_items: int = 0
    blocked_puts: int = 0
    max_queue_size: int = 0
    total_blocked_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_items": self.total_items,
            "dropped_items": self.dropped_items,
            "blocked_puts": self.blocked_puts,
            "max_queue_size": self.max_queue_size,
            "total_blocked_ms": self.total_blocked_ms,
            "drop_rate": self.dropped_items / max(self.total_items, 1),
        }


class BackpressureMonitor:
    """Monitors backpressure in streaming operations.

    Tracks queue depths, blocked operations, and dropped items.
    Useful for diagnosing streaming performance issues.

    Example:
        monitor = BackpressureMonitor(high_water_mark=80)

        # Check if we should slow down
        if monitor.should_throttle():
            await asyncio.sleep(0.01)

        # Record events
        monitor.record_put(queue_size=50)
        monitor.record_blocked(blocked_ms=10.5)
    """

    def __init__(
        self,
        *,
        high_water_mark: int = 80,
        low_water_mark: int = 20,
    ) -> None:
        """Initialize monitor.

        Args:
            high_water_mark: Queue fill % to trigger throttling.
            low_water_mark: Queue fill % to stop throttling.
        """
        self._high_water = high_water_mark
        self._low_water = low_water_mark
        self._stats = BackpressureStats()
        self._current_fill_pct = 0.0
        self._throttling = False

    @property
    def stats(self) -> BackpressureStats:
        """Get current statistics."""
        return self._stats

    def record_put(self, queue_size: int, max_size: int = 100) -> None:
        """Record a put operation."""
        self._stats.total_items += 1
        self._stats.max_queue_size = max(self._stats.max_queue_size, queue_size)
        self._current_fill_pct = (queue_size / max_size) * 100 if max_size > 0 else 0

        # Update throttling state
        if self._current_fill_pct >= self._high_water:
            self._throttling = True
        elif self._current_fill_pct <= self._low_water:
            self._throttling = False

    def record_blocked(self, blocked_ms: float) -> None:
        """Record a blocked put operation."""
        self._stats.blocked_puts += 1
        self._stats.total_blocked_ms += blocked_ms

    def record_drop(self) -> None:
        """Record a dropped item."""
        self._stats.dropped_items += 1

    def should_throttle(self) -> bool:
        """Check if producer should throttle."""
        return self._throttling

    @property
    def fill_percentage(self) -> float:
        """Current queue fill percentage."""
        return self._current_fill_pct


class ChunkQueue(Generic[T]):
    """Async queue with backpressure support for streaming chunks.

    Features:
    - Configurable max size with backpressure
    - Optional item dropping on overflow
    - Async iteration support
    - Backpressure monitoring
    - Optional telemetry event emission

    Example:
        queue = ChunkQueue[AudioChunk](max_size=100)

        # Producer
        await queue.put(chunk)  # Blocks if full

        # Consumer
        async for chunk in queue:
            process(chunk)

        # Signal end
        await queue.close()

        # With telemetry
        def emit(event_type, data):
            print(f"{event_type}: {data}")

        queue = ChunkQueue[AudioChunk](max_size=100, event_emitter=emit)
    """

    def __init__(
        self,
        max_size: int = 100,
        *,
        drop_on_overflow: bool = False,
        event_emitter: EventEmitter | None = None,
    ) -> None:
        """Initialize queue.

        Args:
            max_size: Maximum queue size.
            drop_on_overflow: If True, drop oldest items on overflow instead of blocking.
            event_emitter: Optional callback for telemetry events.
        """
        self._queue: asyncio.Queue[T | None] = asyncio.Queue(maxsize=max_size)
        self._max_size = max_size
        self._drop_on_overflow = drop_on_overflow
        self._closed = False
        self._monitor = BackpressureMonitor()
        self._event_emitter = event_emitter
        self._throttle_active = False

    @property
    def monitor(self) -> BackpressureMonitor:
        """Get backpressure monitor."""
        return self._monitor

    def _emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit a telemetry event if emitter is configured."""
        if self._event_emitter is not None:
            try:
                self._event_emitter(event_type, data)
            except Exception:
                pass  # Don't let telemetry errors affect queue operation

    async def put(self, item: T) -> bool:
        """Put an item in the queue.

        Args:
            item: The item to add.

        Returns:
            True if added, False if dropped.
        """
        if self._closed:
            return False

        start = datetime.now(UTC)

        if self._drop_on_overflow and self._queue.full():
            # Drop oldest item
            try:
                self._queue.get_nowait()
                self._monitor.record_drop()
                self._emit_event("stream.chunk_dropped", {
                    "queue_size": self._queue.qsize(),
                    "max_size": self._max_size,
                    "reason": "overflow",
                })
            except asyncio.QueueEmpty:
                pass

        try:
            if self._drop_on_overflow:
                self._queue.put_nowait(item)
            else:
                await self._queue.put(item)

            elapsed_ms = (datetime.now(UTC) - start).total_seconds() * 1000
            if elapsed_ms > 1:  # Was blocked
                self._monitor.record_blocked(elapsed_ms)
                self._emit_event("stream.producer_blocked", {
                    "blocked_ms": elapsed_ms,
                    "queue_size": self._queue.qsize(),
                })

            self._monitor.record_put(self._queue.qsize(), self._max_size)

            # Emit throttle state changes
            if self._monitor.should_throttle() and not self._throttle_active:
                self._throttle_active = True
                self._emit_event("stream.throttle_started", {
                    "fill_percentage": self._monitor.fill_percentage,
                    "queue_size": self._queue.qsize(),
                })
            elif not self._monitor.should_throttle() and self._throttle_active:
                self._throttle_active = False
                self._emit_event("stream.throttle_ended", {
                    "fill_percentage": self._monitor.fill_percentage,
                    "queue_size": self._queue.qsize(),
                })

            return True

        except asyncio.QueueFull:
            self._monitor.record_drop()
            self._emit_event("stream.chunk_dropped", {
                "queue_size": self._queue.qsize(),
                "max_size": self._max_size,
                "reason": "queue_full",
            })
            return False

    async def get(self) -> T | None:
        """Get an item from the queue.

        Returns:
            The item, or None if queue is closed.
        """
        # Check if closed and empty before blocking
        if self._closed and self._queue.empty():
            return None
        try:
            item = self._queue.get_nowait()
            return item
        except asyncio.QueueEmpty:
            # Queue is empty but not closed, wait for item
            if self._closed:
                return None
            item = await self._queue.get()
            return item

    def get_nowait(self) -> T | None:
        """Get an item without waiting.

        Returns:
            The item, or None if empty.

        Raises:
            asyncio.QueueEmpty: If queue is empty.
        """
        return self._queue.get_nowait()

    async def close(self) -> None:
        """Close the queue."""
        self._closed = True
        # Emit final stats
        self._emit_event("stream.queue_closed", {
            "total_items": self._monitor.stats.total_items,
            "dropped_items": self._monitor.stats.dropped_items,
            "blocked_puts": self._monitor.stats.blocked_puts,
            "max_queue_size": self._monitor.stats.max_queue_size,
            "total_blocked_ms": self._monitor.stats.total_blocked_ms,
        })
        # Try to signal end without blocking or dropping items
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass  # Will be detected via _closed flag in get()

    @property
    def is_closed(self) -> bool:
        """Check if queue is closed."""
        return self._closed

    def __len__(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()

    def __aiter__(self) -> AsyncIterator[T]:
        """Iterate over queue items."""
        return self

    async def __anext__(self) -> T:
        """Get next item."""
        item = await self.get()
        if item is None:
            raise StopAsyncIteration
        return item


class StreamingBuffer:
    """Buffer for accumulating streaming data.

    Provides jitter buffering and chunk coalescing for smoother playback.
    Supports optional telemetry event emission for observability.

    Example:
        buffer = StreamingBuffer(
            target_duration_ms=200,
            max_duration_ms=1000,
        )

        # Add incoming chunks
        buffer.add_chunk(chunk)

        # Read when ready
        if buffer.is_ready():
            data = buffer.read(duration_ms=50)

        # With telemetry
        def emit(event_type, data):
            print(f"{event_type}: {data}")

        buffer = StreamingBuffer(event_emitter=emit)
    """

    def __init__(
        self,
        *,
        target_duration_ms: float = 200,
        max_duration_ms: float = 2000,
        sample_rate: int = 16000,
        channels: int = 1,
        event_emitter: EventEmitter | None = None,
    ) -> None:
        """Initialize buffer.

        Args:
            target_duration_ms: Target buffer level before reads.
            max_duration_ms: Maximum buffer size.
            sample_rate: Audio sample rate.
            channels: Number of audio channels.
            event_emitter: Optional callback for telemetry events.
        """
        self._target_ms = target_duration_ms
        self._max_ms = max_duration_ms
        self._sample_rate = sample_rate
        self._channels = channels
        self._buffer = bytearray()
        self._bytes_per_sample = 2  # PCM_16
        self._total_received = 0
        self._total_read = 0
        self._total_dropped = 0
        self._event_emitter = event_emitter
        self._underrun_active = False

    @property
    def duration_ms(self) -> float:
        """Current buffer duration in milliseconds."""
        samples = len(self._buffer) / (self._bytes_per_sample * self._channels)
        return (samples / self._sample_rate) * 1000

    def is_ready(self) -> bool:
        """Check if buffer has reached target level."""
        return self.duration_ms >= self._target_ms

    def is_full(self) -> bool:
        """Check if buffer is at maximum."""
        return self.duration_ms >= self._max_ms

    def _emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit a telemetry event if emitter is configured."""
        if self._event_emitter is not None:
            try:
                self._event_emitter(event_type, data)
            except Exception:
                pass  # Don't let telemetry errors affect buffer operation

    def add_chunk(self, chunk: AudioChunk) -> int:
        """Add a chunk to the buffer.

        Args:
            chunk: The audio chunk to add.

        Returns:
            Number of bytes dropped if buffer was full.
        """
        dropped = 0

        # Drop oldest data if over max
        while self.duration_ms + chunk.duration_ms > self._max_ms:
            bytes_to_drop = int(
                (self._sample_rate * self._channels * self._bytes_per_sample) / 1000 * 50
            )  # Drop 50ms
            if len(self._buffer) <= bytes_to_drop:
                break
            self._buffer = self._buffer[bytes_to_drop:]
            dropped += bytes_to_drop

        if dropped > 0:
            self._total_dropped += dropped
            self._emit_event("stream.buffer_overflow", {
                "bytes_dropped": dropped,
                "buffer_duration_ms": self.duration_ms,
                "max_duration_ms": self._max_ms,
            })

        self._buffer.extend(chunk.data)
        self._total_received += len(chunk.data)
        return dropped

    def read(self, duration_ms: float = 20) -> bytes:
        """Read data from the buffer.

        Args:
            duration_ms: Duration to read in milliseconds.

        Returns:
            Audio bytes (may be less than requested if buffer is low).
        """
        bytes_to_read = int(
            (self._sample_rate * self._channels * self._bytes_per_sample) / 1000 * duration_ms
        )
        bytes_requested = bytes_to_read
        bytes_to_read = min(bytes_to_read, len(self._buffer))

        # Detect underrun (requested more than available)
        if bytes_to_read < bytes_requested:
            if not self._underrun_active:
                self._underrun_active = True
                self._emit_event("stream.buffer_underrun", {
                    "bytes_requested": bytes_requested,
                    "bytes_available": bytes_to_read,
                    "buffer_duration_ms": self.duration_ms,
                })
        elif self._underrun_active:
            self._underrun_active = False
            self._emit_event("stream.buffer_recovered", {
                "buffer_duration_ms": self.duration_ms,
            })

        data = bytes(self._buffer[:bytes_to_read])
        self._buffer = self._buffer[bytes_to_read:]
        self._total_read += len(data)
        return data

    def clear(self) -> None:
        """Clear the buffer."""
        self._buffer.clear()

    @property
    def stats(self) -> dict[str, Any]:
        """Get buffer statistics."""
        return {
            "duration_ms": self.duration_ms,
            "bytes_buffered": len(self._buffer),
            "total_received": self._total_received,
            "total_read": self._total_read,
            "total_dropped": self._total_dropped,
            "is_ready": self.is_ready(),
            "underrun_active": self._underrun_active,
        }


def encode_audio_for_logging(data: bytes, max_bytes: int = 100) -> str:
    """Encode audio data for safe logging.

    Binary audio data can corrupt logs. This helper provides safe encoding.

    Args:
        data: Raw audio bytes.
        max_bytes: Maximum bytes to include (rest is truncated).

    Returns:
        Safe string representation for logging.
    """
    truncated = len(data) > max_bytes
    sample = data[:max_bytes]
    encoded = base64.b64encode(sample).decode("ascii")

    if truncated:
        return f"<audio:{len(data)}B,sample:{encoded}...>"
    return f"<audio:{len(data)}B,data:{encoded}>"


def calculate_audio_duration_ms(
    byte_count: int,
    sample_rate: int = 16000,
    channels: int = 1,
    bytes_per_sample: int = 2,
) -> float:
    """Calculate audio duration from byte count.

    Args:
        byte_count: Number of audio bytes.
        sample_rate: Sample rate in Hz.
        channels: Number of channels.
        bytes_per_sample: Bytes per sample (2 for PCM_16).

    Returns:
        Duration in milliseconds.
    """
    samples = byte_count / (bytes_per_sample * channels)
    return (samples / sample_rate) * 1000


__all__ = [
    "AudioChunk",
    "AudioFormat",
    "BackpressureMonitor",
    "BackpressureStats",
    "ChunkQueue",
    "EventEmitter",
    "StreamConfig",
    "StreamingBuffer",
    "calculate_audio_duration_ms",
    "encode_audio_for_logging",
]
