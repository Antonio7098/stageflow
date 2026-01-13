"""Tests for the streaming primitives helper module."""

from __future__ import annotations

import asyncio
import pytest

from stageflow.helpers.streaming import (
    AudioChunk,
    AudioFormat,
    StreamConfig,
    ChunkQueue,
    StreamingBuffer,
    BackpressureMonitor,
    encode_audio_for_logging,
    calculate_audio_duration_ms,
)


class TestAudioChunk:
    """Tests for AudioChunk dataclass."""

    def test_duration_calculation(self):
        """Should calculate duration from data size."""
        # 16kHz, 16-bit mono = 32000 bytes/sec = 32 bytes/ms
        chunk = AudioChunk(
            data=b"\x00" * 3200,  # 100ms of audio
            sample_rate=16000,
            channels=1,
            format=AudioFormat.PCM_16,
        )

        assert abs(chunk.duration_ms - 100.0) < 0.1

    def test_to_dict_encodes_data(self):
        """Should base64 encode audio data."""
        chunk = AudioChunk(
            data=b"\x00\x01\x02\x03",
            sample_rate=16000,
        )

        result = chunk.to_dict()

        assert isinstance(result["data"], str)
        assert result["sample_rate"] == 16000

    def test_from_dict_decodes_data(self):
        """Should decode base64 audio data."""
        chunk = AudioChunk(data=b"hello audio", sample_rate=24000)
        serialized = chunk.to_dict()

        restored = AudioChunk.from_dict(serialized)

        assert restored.data == b"hello audio"
        assert restored.sample_rate == 24000

    def test_metadata_preserved(self):
        """Should preserve metadata through serialization."""
        chunk = AudioChunk(
            data=b"test",
            metadata={"source": "microphone", "quality": "high"},
        )

        restored = AudioChunk.from_dict(chunk.to_dict())

        assert restored.metadata["source"] == "microphone"
        assert restored.metadata["quality"] == "high"


class TestBackpressureMonitor:
    """Tests for BackpressureMonitor."""

    def test_records_put_operations(self):
        """Should track put operations."""
        monitor = BackpressureMonitor()

        monitor.record_put(queue_size=50, max_size=100)
        monitor.record_put(queue_size=60, max_size=100)

        assert monitor.stats.total_items == 2
        assert monitor.stats.max_queue_size == 60

    def test_throttling_triggers_at_high_water(self):
        """Should trigger throttling at high water mark."""
        monitor = BackpressureMonitor(high_water_mark=80, low_water_mark=20)

        monitor.record_put(queue_size=50, max_size=100)
        assert not monitor.should_throttle()

        monitor.record_put(queue_size=85, max_size=100)
        assert monitor.should_throttle()

    def test_throttling_releases_at_low_water(self):
        """Should release throttling at low water mark."""
        monitor = BackpressureMonitor(high_water_mark=80, low_water_mark=20)

        # Trigger throttling
        monitor.record_put(queue_size=85, max_size=100)
        assert monitor.should_throttle()

        # Stay throttled above low water
        monitor.record_put(queue_size=30, max_size=100)
        assert monitor.should_throttle()

        # Release at low water
        monitor.record_put(queue_size=15, max_size=100)
        assert not monitor.should_throttle()

    def test_records_blocked_operations(self):
        """Should track blocked operations."""
        monitor = BackpressureMonitor()

        monitor.record_blocked(blocked_ms=50.0)
        monitor.record_blocked(blocked_ms=30.0)

        assert monitor.stats.blocked_puts == 2
        assert monitor.stats.total_blocked_ms == 80.0

    def test_records_dropped_items(self):
        """Should track dropped items."""
        monitor = BackpressureMonitor()

        monitor.record_drop()
        monitor.record_drop()
        monitor.record_drop()

        assert monitor.stats.dropped_items == 3


class TestChunkQueue:
    """Tests for ChunkQueue."""

    @pytest.mark.asyncio
    async def test_put_and_get(self):
        """Should put and get items."""
        queue: ChunkQueue[str] = ChunkQueue(max_size=10)

        await queue.put("item1")
        await queue.put("item2")

        assert await queue.get() == "item1"
        assert await queue.get() == "item2"

    @pytest.mark.asyncio
    async def test_async_iteration(self):
        """Should support async iteration."""
        queue: ChunkQueue[int] = ChunkQueue(max_size=10)

        # Add items
        for i in range(5):
            await queue.put(i)
        await queue.close()

        # Iterate
        items = []
        async for item in queue:
            items.append(item)

        assert items == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_drop_on_overflow(self):
        """Should drop oldest items when configured."""
        queue: ChunkQueue[int] = ChunkQueue(max_size=3, drop_on_overflow=True)

        await queue.put(1)
        await queue.put(2)
        await queue.put(3)
        await queue.put(4)  # Should drop 1
        await queue.put(5)  # Should drop 2

        assert queue.monitor.stats.dropped_items == 2
        assert len(queue) == 3

        # Should get 3, 4, 5
        await queue.close()
        items = [item async for item in queue]
        assert items == [3, 4, 5]

    @pytest.mark.asyncio
    async def test_close_signals_end(self):
        """Closing queue should signal end to consumers."""
        queue: ChunkQueue[str] = ChunkQueue(max_size=10)

        await queue.put("item")
        await queue.close()

        assert await queue.get() == "item"
        assert await queue.get() is None  # Signal end

    @pytest.mark.asyncio
    async def test_backpressure_monitoring(self):
        """Should update backpressure monitor."""
        queue: ChunkQueue[int] = ChunkQueue(max_size=10)

        for i in range(7):
            await queue.put(i)

        assert queue.monitor.stats.total_items == 7
        assert queue.monitor.fill_percentage == 70.0


class TestStreamingBuffer:
    """Tests for StreamingBuffer."""

    def test_add_and_read_chunks(self):
        """Should accumulate and read chunks."""
        buffer = StreamingBuffer(
            target_duration_ms=100,
            sample_rate=16000,
        )

        # Add 100ms of audio (3200 bytes at 16kHz mono 16-bit)
        chunk = AudioChunk(data=b"\x00" * 3200, sample_rate=16000)
        buffer.add_chunk(chunk)

        assert buffer.is_ready()

        # Read 50ms
        data = buffer.read(duration_ms=50)
        assert len(data) == 1600  # 50ms worth

    def test_target_duration_check(self):
        """Should report ready when target reached."""
        buffer = StreamingBuffer(target_duration_ms=200)

        # Add 100ms - not ready
        buffer.add_chunk(AudioChunk(data=b"\x00" * 3200))
        assert not buffer.is_ready()

        # Add another 100ms - now ready
        buffer.add_chunk(AudioChunk(data=b"\x00" * 3200))
        assert buffer.is_ready()

    def test_max_duration_drops_old_data(self):
        """Should drop old data when max duration exceeded."""
        buffer = StreamingBuffer(
            target_duration_ms=100,
            max_duration_ms=200,
        )

        # Add 300ms of audio
        for _ in range(3):
            buffer.add_chunk(AudioChunk(data=b"\x00" * 3200))

        # Should be capped near max
        assert buffer.duration_ms <= 250  # Some tolerance

    def test_stats(self):
        """Should provide buffer statistics."""
        buffer = StreamingBuffer(target_duration_ms=100)

        buffer.add_chunk(AudioChunk(data=b"\x00" * 1600))
        buffer.read(duration_ms=25)

        stats = buffer.stats

        assert stats["total_received"] == 1600
        assert stats["total_read"] == 800  # 25ms at 16kHz
        assert "duration_ms" in stats
        assert "is_ready" in stats

    def test_clear(self):
        """Should clear the buffer."""
        buffer = StreamingBuffer()

        buffer.add_chunk(AudioChunk(data=b"\x00" * 3200))
        buffer.clear()

        assert buffer.duration_ms == 0


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_encode_audio_for_logging(self):
        """Should encode audio safely for logging."""
        audio = b"\x00\x01\x02" * 1000

        result = encode_audio_for_logging(audio, max_bytes=100)

        assert "<audio:" in result
        assert "3000B" in result  # Total size
        assert "sample:" in result

    def test_encode_audio_short_content(self):
        """Should encode short audio without truncation."""
        audio = b"\x00\x01\x02"

        result = encode_audio_for_logging(audio, max_bytes=100)

        assert "..." not in result
        assert "data:" in result

    def test_calculate_audio_duration(self):
        """Should calculate audio duration from bytes."""
        # 16kHz, mono, 16-bit = 32000 bytes/sec
        duration = calculate_audio_duration_ms(
            byte_count=32000,
            sample_rate=16000,
            channels=1,
            bytes_per_sample=2,
        )

        assert duration == 1000.0  # 1 second

    def test_calculate_audio_duration_stereo(self):
        """Should handle stereo audio."""
        # 16kHz, stereo, 16-bit = 64000 bytes/sec
        duration = calculate_audio_duration_ms(
            byte_count=64000,
            sample_rate=16000,
            channels=2,
            bytes_per_sample=2,
        )

        assert duration == 1000.0  # 1 second
