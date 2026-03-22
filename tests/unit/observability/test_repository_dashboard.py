from __future__ import annotations

from stageflow.observability import (
    AlertThresholds,
    InMemoryTelemetryRepository,
    ObservabilityAPI,
    ObservabilityDashboard,
    ObservabilityQueryWindow,
    TelemetryEvent,
    build_graph_availability,
)


class TestRepositoryAndDashboard:
    def test_repository_exposes_agent_graph_and_user_metrics(self) -> None:
        repository = InMemoryTelemetryRepository()
        repository.store_batch(
            [
                TelemetryEvent.model_validate(
                    {
                        "event_name": "pipeline.wide",
                        "event_kind": "trace",
                        "event_version": "v1",
                        "timestamp": "2026-03-20T12:00:00+00:00",
                        "pipeline_run_id": "trace-1",
                        "user_id": "user-1",
                        "session_id": "session-1",
                        "id": "trace-1",
                        "type": "TRACE",
                        "name": "demo",
                        "start_time": "2026-03-20T12:00:00+00:00",
                        "end_time": "2026-03-20T12:00:10+00:00",
                    }
                ),
                TelemetryEvent.model_validate(
                    {
                        "event_name": "stage.wide",
                        "event_kind": "span",
                        "event_version": "v1",
                        "timestamp": "2026-03-20T12:00:01+00:00",
                        "pipeline_run_id": "trace-1",
                        "user_id": "user-1",
                        "session_id": "session-1",
                        "id": "obs-1",
                        "parent_observation_id": "trace-1",
                        "type": "SPAN",
                        "name": "search",
                        "node": "search",
                        "step": 1,
                        "start_time": "2026-03-20T12:00:01+00:00",
                        "end_time": "2026-03-20T12:00:02+00:00",
                        "metadata": {"status": "completed", "duration_ms": 100, "provider": "anthropic", "model_id": "claude", "total_cost": 1.25},
                    }
                ),
                TelemetryEvent.model_validate(
                    {
                        "event_name": "tool.failed",
                        "event_kind": "tool",
                        "event_version": "v1",
                        "timestamp": "2026-03-20T12:00:03+00:00",
                        "pipeline_run_id": "trace-1",
                        "user_id": "user-1",
                        "session_id": "session-1",
                        "duration_ms": 25,
                        "metadata": {"provider": "anthropic", "model_id": "claude", "total_cost": 0.75},
                    }
                ),
            ]
        )

        graph = repository.get_agent_graph_data(trace_id="trace-1")
        metrics = repository.get_user_metrics()
        dashboard = ObservabilityDashboard(repository)
        api = ObservabilityAPI(repository)

        assert [node.id for node in graph] == ["trace-1", "obs-1"]
        assert metrics[0].user_id == "user-1"
        assert metrics[0].observation_count == 3
        assert metrics[0].trace_count == 1
        assert metrics[0].session_count == 1
        assert metrics[0].error_count == 1
        assert metrics[0].total_cost == 2.0
        assert metrics[0].event_kinds == {"trace": 1, "span": 1, "tool": 1}

        timeline = dashboard.get_pipeline_timeline(trace_id="trace-1")
        provider_metrics = dashboard.get_provider_metrics()
        graph_view = dashboard.get_agent_graph_view(trace_id="trace-1")
        insights = dashboard.get_user_insights()
        replay = dashboard.get_replay_view(trace_id="trace-1")
        alerts = dashboard.build_alerts(
            trace_id="trace-1",
            queue_depth=5,
            dropped_events=1,
            thresholds=AlertThresholds(max_error_count=0, max_queue_depth=2, max_drop_count=0),
        )
        graph_response = api.get_agent_graph(window=ObservabilityQueryWindow(trace_id="trace-1"))

        assert len(timeline) == 1
        assert timeline[0]["stage"] == "search"
        assert timeline[0]["duration_ms"] == 100
        assert provider_metrics == [
            {
                "provider": "anthropic",
                "model_id": "claude",
                "call_count": 2,
                "error_count": 1,
                "total_duration_ms": 125.0,
                "total_cost": 2.0,
                "last_event_at": "2026-03-20T12:00:03+00:00",
            }
        ]
        assert len(graph_view) == 2
        assert insights[0]["user_id"] == "user-1"
        assert len(replay) == 3
        assert [alert["code"] for alert in alerts] == [
            "provider_errors_exceeded",
            "queue_depth_exceeded",
            "dropped_events_detected",
        ]
        assert graph_response["trace_id"] == "trace-1"
        assert len(graph_response["nodes"]) == 2
        assert build_graph_availability(graph) is True
