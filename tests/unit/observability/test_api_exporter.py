from __future__ import annotations

import pytest

from stageflow.observability import (
    InMemoryTelemetryRepository,
    ObservabilityAPI,
    ObservabilityAPIError,
    ObservabilityQueryWindow,
    TelemetryEvent,
    TelemetryExporter,
    create_fastapi_router,
)


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object] | None]] = []

    async def emit(self, *, type: str, data: dict[str, object] | None) -> None:
        self.events.append((type, data))

    def try_emit(self, *, type: str, data: dict[str, object] | None) -> None:
        self.events.append((type, data))


class TestObservabilityAPIAndExporter:
    def test_api_returns_dashboard_views(self) -> None:
        repository = InMemoryTelemetryRepository()
        repository.store(
            TelemetryEvent.model_validate(
                {
                    "event_name": "stage.wide",
                    "event_kind": "span",
                    "event_version": "v1",
                    "timestamp": "2026-03-20T12:00:01+00:00",
                    "pipeline_run_id": "trace-1",
                    "id": "obs-1",
                    "type": "SPAN",
                    "name": "search",
                    "start_time": "2026-03-20T12:00:01+00:00",
                    "end_time": "2026-03-20T12:00:02+00:00",
                    "metadata": {"status": "completed", "provider": "anthropic", "model_id": "claude"},
                }
            )
        )

        api = ObservabilityAPI(repository)

        graph = api.get_agent_graph(window=ObservabilityQueryWindow(trace_id="trace-1"))
        timeline = api.get_pipeline_timeline(window=ObservabilityQueryWindow(trace_id="trace-1"))
        provider_metrics = api.get_provider_metrics(trace_id="trace-1")
        replay = api.get_replay(trace_id="trace-1")

        assert len(graph["nodes"]) == 1
        assert timeline["timeline"][0]["stage"] == "search"
        assert provider_metrics["provider_metrics"][0]["provider"] == "anthropic"
        assert replay["records"][0]["event_name"] == "stage.wide"

    @pytest.mark.asyncio
    async def test_exporter_emits_normalized_payloads(self) -> None:
        sink = RecordingSink()
        exporter = TelemetryExporter(sink)

        payload = await exporter.emit(
            event_type="tool.completed",
            ctx=None,
            data={"metadata": {"provider": "anthropic"}, "duration_ms": 12},
        )

        assert payload["event_name"] == "tool.completed"
        assert payload["event_kind"] == "tool"
        assert payload["metadata"]["provider"] == "anthropic"
        assert sink.events[0][0] == "tool.completed"

    @pytest.mark.asyncio
    async def test_exporter_instrument_async_emits_and_returns_callback_result(self) -> None:
        sink = RecordingSink()
        exporter = TelemetryExporter(sink)

        async def callback(_span: object) -> str:
            return "ok"

        result = await exporter.instrument_async(
            span_name="tool-run",
            event_type="tool.started",
            ctx=None,
            callback=callback,
        )

        assert result == "ok"
        assert sink.events[0][0] == "tool.started"

    def test_create_fastapi_router_fails_loudly_without_dependency(self) -> None:
        try:
            import fastapi  # noqa: F401
        except ImportError:
            with pytest.raises(ObservabilityAPIError):
                create_fastapi_router(InMemoryTelemetryRepository())
