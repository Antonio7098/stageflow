from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Sequence
from typing import Any

from stageflow.events.sink import EventSink
from stageflow.observability.repository import InMemoryTelemetryRepository, TelemetryEvent, TelemetryRepository


class TelemetryIngestionService(EventSink):
    def __init__(
        self,
        repository: TelemetryRepository | None = None,
        *,
        max_batch_size: int = 100,
        max_queue_size: int = 1000,
        sample_rate: float = 1.0,
    ) -> None:
        if max_batch_size <= 0:
            raise ValueError("max_batch_size must be > 0")
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be > 0")
        if not 0 < sample_rate <= 1.0:
            raise ValueError("sample_rate must be in the range (0, 1]")
        self._repository = repository or InMemoryTelemetryRepository()
        self._max_batch_size = max_batch_size
        self._queue: asyncio.Queue[tuple[str, dict[str, Any] | None]] = asyncio.Queue(maxsize=max_queue_size)
        self._worker: asyncio.Task[None] | None = None
        self._running = False
        self._sample_rate = sample_rate

    @property
    def repository(self) -> TelemetryRepository:
        return self._repository

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        while not self._queue.empty():
            await self.flush()
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        if not self._running:
            await self.start()
        await self._queue.put((type, data))

    def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        if not self._running:
            raise RuntimeError("TelemetryIngestionService must be started before try_emit")
        self._queue.put_nowait((type, data))

    async def flush(self) -> int:
        batch = await self._dequeue_batch()
        return self._store_batch(batch)

    async def _run(self) -> None:
        while self._running:
            try:
                await self.flush()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.05)

    async def _dequeue_batch(self) -> list[TelemetryEvent]:
        item = await self._queue.get()
        events: list[TelemetryEvent] = []
        normalized = self._normalize_event(*item)
        if normalized is not None:
            events.append(normalized)
        while len(events) < self._max_batch_size:
            try:
                next_item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            next_event = self._normalize_event(*next_item)
            if next_event is not None:
                events.append(next_event)
        return events

    def _store_batch(self, events: Sequence[TelemetryEvent]) -> int:
        if not events:
            return 0
        return self._repository.store_batch(events)

    def _normalize_event(self, event_type: str, payload: dict[str, Any] | None) -> TelemetryEvent | None:
        if not event_type:
            raise ValueError("event_type must not be empty")
        normalized = dict(payload or {})
        normalized.setdefault("event_name", event_type)
        normalized.setdefault("metadata", {})
        event = TelemetryEvent.model_validate(normalized)
        if not self._should_sample(event):
            return None
        return event

    def _should_sample(self, event: TelemetryEvent) -> bool:
        if self._sample_rate >= 1.0:
            return True
        identity = event.trace_id or event.pipeline_run_id or event.request_id or event.event_name
        digest = hashlib.sha1(identity.encode("utf-8"), usedforsecurity=False).hexdigest()
        ratio = int(digest[:8], 16) / 0xFFFFFFFF
        return ratio <= self._sample_rate


__all__ = ["TelemetryIngestionService"]
