from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stageflow.observability.dashboard import AlertThresholds, ObservabilityDashboard
from stageflow.observability.repository import TelemetryRepository


class ObservabilityAPIError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ObservabilityQueryWindow:
    trace_id: str
    min_start_time: str | None = None
    max_start_time: str | None = None


class ObservabilityAPI:
    def __init__(self, repository: TelemetryRepository) -> None:
        self._dashboard = ObservabilityDashboard(repository)

    def get_agent_graph(self, *, window: ObservabilityQueryWindow) -> dict[str, Any]:
        nodes = self._dashboard.get_agent_graph_view(
            trace_id=window.trace_id,
            min_start_time=window.min_start_time,
            max_start_time=window.max_start_time,
        )
        return {"trace_id": window.trace_id, "nodes": nodes}

    def get_pipeline_timeline(self, *, window: ObservabilityQueryWindow) -> dict[str, Any]:
        timeline = self._dashboard.get_pipeline_timeline(
            trace_id=window.trace_id,
            min_start_time=window.min_start_time,
            max_start_time=window.max_start_time,
        )
        return {"trace_id": window.trace_id, "timeline": timeline}

    def get_provider_metrics(self, *, trace_id: str | None = None) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "provider_metrics": self._dashboard.get_provider_metrics(trace_id=trace_id),
        }

    def get_user_insights(self, *, user_ids: list[str] | None = None) -> dict[str, Any]:
        return {"user_ids": user_ids or [], "users": self._dashboard.get_user_insights(user_ids=user_ids)}

    def get_replay(self, *, trace_id: str) -> dict[str, Any]:
        return {"trace_id": trace_id, "records": self._dashboard.get_replay_view(trace_id=trace_id)}

    def get_alerts(
        self,
        *,
        trace_id: str | None = None,
        queue_depth: int = 0,
        dropped_events: int = 0,
        thresholds: AlertThresholds | None = None,
    ) -> dict[str, Any]:
        alerts = self._dashboard.build_alerts(
            trace_id=trace_id,
            queue_depth=queue_depth,
            dropped_events=dropped_events,
            thresholds=thresholds,
        )
        return {"trace_id": trace_id, "alerts": alerts}


def create_fastapi_router(repository: TelemetryRepository) -> Any:
    try:
        from fastapi import APIRouter, Query
    except ImportError as exc:
        raise ObservabilityAPIError("FastAPI must be installed to create the observability router") from exc

    api = ObservabilityAPI(repository)
    router = APIRouter(prefix="/observability", tags=["observability"])

    @router.get("/agent-graph")
    def get_agent_graph(
        trace_id: str,
        min_start_time: str | None = Query(default=None),
        max_start_time: str | None = Query(default=None),
    ) -> dict[str, Any]:
        return api.get_agent_graph(
            window=ObservabilityQueryWindow(
                trace_id=trace_id,
                min_start_time=min_start_time,
                max_start_time=max_start_time,
            )
        )

    @router.get("/pipeline-timeline")
    def get_pipeline_timeline(
        trace_id: str,
        min_start_time: str | None = Query(default=None),
        max_start_time: str | None = Query(default=None),
    ) -> dict[str, Any]:
        return api.get_pipeline_timeline(
            window=ObservabilityQueryWindow(
                trace_id=trace_id,
                min_start_time=min_start_time,
                max_start_time=max_start_time,
            )
        )

    @router.get("/provider-metrics")
    def get_provider_metrics(trace_id: str | None = Query(default=None)) -> dict[str, Any]:
        return api.get_provider_metrics(trace_id=trace_id)

    @router.get("/user-insights")
    def get_user_insights(user_ids: list[str] | None = Query(default=None)) -> dict[str, Any]:
        return api.get_user_insights(user_ids=user_ids)

    @router.get("/replay")
    def get_replay(trace_id: str) -> dict[str, Any]:
        return api.get_replay(trace_id=trace_id)

    @router.get("/alerts")
    def get_alerts(
        trace_id: str | None = Query(default=None),
        queue_depth: int = Query(default=0, ge=0),
        dropped_events: int = Query(default=0, ge=0),
        max_error_count: int = Query(default=0, ge=0),
        max_queue_depth: int = Query(default=0, ge=0),
        max_drop_count: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return api.get_alerts(
            trace_id=trace_id,
            queue_depth=queue_depth,
            dropped_events=dropped_events,
            thresholds=AlertThresholds(
                max_error_count=max_error_count,
                max_queue_depth=max_queue_depth,
                max_drop_count=max_drop_count,
            ),
        )

    return router


__all__ = [
    "ObservabilityAPI",
    "ObservabilityAPIError",
    "ObservabilityQueryWindow",
    "create_fastapi_router",
]
