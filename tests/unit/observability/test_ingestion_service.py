from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from stageflow.observability import (
    InMemoryTelemetryRepository,
    TelemetryBackpressureError,
    TelemetryIngestionError,
    TelemetryIngestionService,
    compute_ingestion_delay_ms,
)


class TestTelemetryIngestionService:
    def test_invalid_configuration_fails_fast(self) -> None:
        with pytest.raises(ValueError):
            TelemetryIngestionService(max_batch_size=0)
        with pytest.raises(ValueError):
            TelemetryIngestionService(max_queue_size=0)
        with pytest.raises(ValueError):
            TelemetryIngestionService(sample_rate=0)

    def test_compute_ingestion_delay_matches_boundary_policy(self) -> None:
        assert compute_ingestion_delay_ms(source="otel") == 0
        assert (
            compute_ingestion_delay_ms(
                now=datetime(2026, 3, 20, 23, 50, tzinfo=UTC),
                default_delay_ms=9000,
            )
            == 9000
        )
        assert (
            compute_ingestion_delay_ms(
                now=datetime(2026, 3, 20, 12, 0, tzinfo=UTC),
                default_delay_ms=9000,
            )
            == 5000
        )

    @pytest.mark.asyncio
    async def test_try_emit_requires_started_service(self) -> None:
        service = TelemetryIngestionService()
        with pytest.raises(RuntimeError):
            service.try_emit(type="stage.wide", data={"event_name": "stage.wide", "event_kind": "span", "event_version": "v1", "timestamp": "2026-03-20T12:00:00+00:00"})

    @pytest.mark.asyncio
    async def test_emit_persists_events(self) -> None:
        repository = InMemoryTelemetryRepository()
        service = TelemetryIngestionService(repository=repository)

        await service.emit(
            type="stage.wide",
            data={
                "event_name": "stage.wide",
                "event_kind": "span",
                "event_version": "v1",
                "timestamp": "2026-03-20T12:00:00+00:00",
                "pipeline_run_id": "trace-1",
                "id": "obs-1",
                "start_time": "2026-03-20T12:00:00+00:00",
                "metadata": {},
            },
        )
        await asyncio.sleep(0.1)
        await service.stop()

        events = repository.list_events()
        assert len(events) == 1
        assert events[0].event_name == "stage.wide"
        assert events[0].pipeline_run_id == "trace-1"
        assert service.metrics.enqueued == 1
        assert service.metrics.persisted == 1
        assert service.metrics.batches_processed >= 1

    @pytest.mark.asyncio
    async def test_sampling_can_drop_events(self, monkeypatch) -> None:
        repository = InMemoryTelemetryRepository()
        service = TelemetryIngestionService(repository=repository)
        monkeypatch.setattr(service, "_should_sample", lambda event: False)

        await service.emit(
            type="tool.completed",
            data={
                "event_name": "tool.completed",
                "event_kind": "tool",
                "event_version": "v1",
                "timestamp": "2026-03-20T12:00:00+00:00",
                "metadata": {},
            },
        )
        await asyncio.sleep(0.1)
        await service.stop()

        assert repository.list_events() == []
        assert service.metrics.dropped >= 1

    @pytest.mark.asyncio
    async def test_backpressure_marks_service_unhealthy(self) -> None:
        service = TelemetryIngestionService(max_queue_size=1)
        await service.start()

        service.try_emit(
            type="stage.wide",
            data={
                "event_name": "stage.wide",
                "event_kind": "span",
                "event_version": "v1",
                "timestamp": "2026-03-20T12:00:00+00:00",
                "metadata": {},
            },
        )

        with pytest.raises(TelemetryBackpressureError):
            service.try_emit(
                type="stage.wide",
                data={
                    "event_name": "stage.wide",
                    "event_kind": "span",
                    "event_version": "v1",
                    "timestamp": "2026-03-20T12:00:01+00:00",
                    "metadata": {},
                },
            )

        assert service.is_healthy is False
        assert service.metrics.queue_full_count == 1

        with pytest.raises(TelemetryIngestionError):
            await service.stop(drain=False)
