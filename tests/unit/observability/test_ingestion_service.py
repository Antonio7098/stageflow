from __future__ import annotations

import asyncio

import pytest

from stageflow.observability import InMemoryTelemetryRepository, TelemetryIngestionService


class TestTelemetryIngestionService:
    def test_invalid_configuration_fails_fast(self) -> None:
        with pytest.raises(ValueError):
            TelemetryIngestionService(max_batch_size=0)
        with pytest.raises(ValueError):
            TelemetryIngestionService(max_queue_size=0)
        with pytest.raises(ValueError):
            TelemetryIngestionService(sample_rate=0)

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
