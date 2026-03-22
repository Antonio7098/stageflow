from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from stageflow.events.sink import EventSink
from stageflow.observability.repository import InMemoryTelemetryRepository, TelemetryEvent, TelemetryRepository


logger = logging.getLogger("stageflow.observability.ingestion")


class TelemetryIngestionError(RuntimeError):
    pass


class TelemetryBackpressureError(TelemetryIngestionError):
    pass


@dataclass(slots=True)
class TelemetryIngestionMetrics:
    enqueued: int = 0
    persisted: int = 0
    dropped: int = 0
    queue_full_count: int = 0
    batches_processed: int = 0
    last_flush_started_at: str | None = None
    last_flush_completed_at: str | None = None
    last_error_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_ingestion_delay_ms(
    *,
    now: datetime | None = None,
    requested_delay_ms: int | None = None,
    default_delay_ms: int = 5000,
    source: str = "api",
) -> int:
    if requested_delay_ms is not None:
        if requested_delay_ms < 0:
            raise ValueError("requested_delay_ms must be >= 0")
        return requested_delay_ms

    now = now or datetime.now(UTC)
    if (now.hour == 23 and now.minute >= 45) or (now.hour == 0 and now.minute <= 15):
        return default_delay_ms
    if source == "otel":
        return 0
    return min(5000, default_delay_ms)


class TelemetryIngestionService(EventSink):
    def __init__(
        self,
        repository: TelemetryRepository | None = None,
        *,
        max_batch_size: int = 100,
        max_queue_size: int = 1000,
        sample_rate: float = 1.0,
        flush_interval_seconds: float = 0.05,
        default_delay_ms: int = 5000,
    ) -> None:
        if max_batch_size <= 0:
            raise ValueError("max_batch_size must be > 0")
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be > 0")
        if not 0 < sample_rate <= 1.0:
            raise ValueError("sample_rate must be in the range (0, 1]")
        if flush_interval_seconds <= 0:
            raise ValueError("flush_interval_seconds must be > 0")
        if default_delay_ms < 0:
            raise ValueError("default_delay_ms must be >= 0")
        self._repository = repository or InMemoryTelemetryRepository()
        self._max_batch_size = max_batch_size
        self._queue: asyncio.Queue[tuple[str, dict[str, Any] | None]] = asyncio.Queue(maxsize=max_queue_size)
        self._worker: asyncio.Task[None] | None = None
        self._running = False
        self._sample_rate = sample_rate
        self._flush_interval_seconds = flush_interval_seconds
        self._default_delay_ms = default_delay_ms
        self._metrics = TelemetryIngestionMetrics()
        self._last_error: Exception | None = None

    @property
    def repository(self) -> TelemetryRepository:
        return self._repository

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def metrics(self) -> TelemetryIngestionMetrics:
        return self._metrics

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def last_error(self) -> Exception | None:
        return self._last_error

    @property
    def is_healthy(self) -> bool:
        return self._last_error is None

    async def start(self) -> None:
        if self._running:
            self._raise_if_unhealthy()
            return
        self._last_error = None
        self._running = True
        self._worker = asyncio.create_task(self._run())

    async def stop(self, *, drain: bool = True, timeout: float = 5.0) -> None:
        if not self._running:
            self._raise_if_unhealthy()
            return
        self._running = False
        if drain and not self._queue.empty():
            await asyncio.wait_for(self.drain(), timeout=timeout)
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None
        self._raise_if_unhealthy()

    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        self._raise_if_unhealthy()
        if not self._running:
            await self.start()
        self._metrics.enqueued += 1
        await self._queue.put((type, data))

    def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        self._raise_if_unhealthy()
        if not self._running:
            raise RuntimeError("TelemetryIngestionService must be started before try_emit")
        try:
            self._queue.put_nowait((type, data))
        except asyncio.QueueFull as exc:
            self._metrics.dropped += 1
            self._metrics.queue_full_count += 1
            self._record_error(TelemetryBackpressureError("telemetry ingestion queue is full"))
            raise TelemetryBackpressureError("telemetry ingestion queue is full") from exc
        self._metrics.enqueued += 1

    async def flush(self) -> int:
        self._raise_if_unhealthy()
        batch = await self._dequeue_batch()
        return self._store_batch(batch)

    async def drain(self) -> int:
        flushed = 0
        while not self._queue.empty():
            flushed += await self.flush()
        return flushed

    def get_delay_ms(self, *, requested_delay_ms: int | None = None, source: str = "api") -> int:
        return compute_ingestion_delay_ms(
            requested_delay_ms=requested_delay_ms,
            default_delay_ms=self._default_delay_ms,
            source=source,
        )

    async def _run(self) -> None:
        while self._running:
            try:
                await self.flush()
            except asyncio.QueueEmpty:
                await asyncio.sleep(self._flush_interval_seconds)
            except Exception as exc:
                self._record_error(exc)
                logger.exception("Telemetry ingestion worker failed")
                self._running = False
                return

    async def _dequeue_batch(self) -> list[TelemetryEvent]:
        pulled = 0
        item = await self._queue.get()
        pulled += 1
        events: list[TelemetryEvent] = []
        try:
            normalized = self._normalize_event(*item)
            if normalized is not None:
                events.append(normalized)
            while len(events) < self._max_batch_size:
                try:
                    next_item = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                pulled += 1
                next_event = self._normalize_event(*next_item)
                if next_event is not None:
                    events.append(next_event)
            return events
        finally:
            for _ in range(pulled):
                self._queue.task_done()

    def _store_batch(self, events: Sequence[TelemetryEvent]) -> int:
        if not events:
            return 0
        self._metrics.last_flush_started_at = datetime.now(UTC).isoformat()
        persisted = self._repository.store_batch(events)
        self._metrics.persisted += persisted
        self._metrics.batches_processed += 1
        self._metrics.last_flush_completed_at = datetime.now(UTC).isoformat()
        return persisted

    def _normalize_event(self, event_type: str, payload: dict[str, Any] | None) -> TelemetryEvent | None:
        if not event_type:
            raise ValueError("event_type must not be empty")
        normalized = dict(payload or {})
        normalized.setdefault("event_name", event_type)
        normalized.setdefault("metadata", {})
        event = TelemetryEvent.model_validate(normalized)
        if not self._should_sample(event):
            self._metrics.dropped += 1
            return None
        return event

    def _should_sample(self, event: TelemetryEvent) -> bool:
        if self._sample_rate >= 1.0:
            return True
        identity = event.trace_id or event.pipeline_run_id or event.request_id or event.event_name
        digest = hashlib.sha1(identity.encode("utf-8"), usedforsecurity=False).hexdigest()
        ratio = int(digest[:8], 16) / 0xFFFFFFFF
        return ratio <= self._sample_rate

    def _raise_if_unhealthy(self) -> None:
        if self._last_error is not None:
            raise TelemetryIngestionError("telemetry ingestion service is unhealthy") from self._last_error

    def _record_error(self, error: Exception) -> None:
        self._last_error = error
        self._metrics.last_error_at = datetime.now(UTC).isoformat()


__all__ = [
    "TelemetryBackpressureError",
    "TelemetryIngestionError",
    "TelemetryIngestionMetrics",
    "TelemetryIngestionService",
    "compute_ingestion_delay_ms",
]
