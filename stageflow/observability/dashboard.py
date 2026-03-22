from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from stageflow.observability.repository import (
    AgentGraphNode,
    TelemetryRepository,
    serialize_agent_graph,
    serialize_provider_metrics,
    serialize_replay_records,
    serialize_user_metrics,
)


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    stage: str
    status: str
    started_at: str
    ended_at: str | None
    duration_ms: int | None
    node: str | None
    step: int | None


@dataclass(frozen=True, slots=True)
class AlertThresholds:
    max_error_count: int = 0
    max_queue_depth: int = 0
    max_drop_count: int = 0


@dataclass(frozen=True, slots=True)
class AlertRecord:
    severity: str
    code: str
    message: str
    context: dict[str, Any]


class ObservabilityDashboard:
    def __init__(self, repository: TelemetryRepository) -> None:
        self._repository = repository

    def get_agent_graph_view(
        self,
        *,
        trace_id: str,
        min_start_time: str | None = None,
        max_start_time: str | None = None,
    ) -> list[dict[str, Any]]:
        return serialize_agent_graph(
            self._repository.get_agent_graph_data(
                trace_id=trace_id,
                min_start_time=min_start_time,
                max_start_time=max_start_time,
            )
        )

    def get_pipeline_timeline(
        self,
        *,
        trace_id: str,
        min_start_time: str | None = None,
        max_start_time: str | None = None,
    ) -> list[dict[str, Any]]:
        entries: list[TimelineEntry] = []
        for node in self._repository.get_agent_graph_data(
            trace_id=trace_id,
            min_start_time=min_start_time,
            max_start_time=max_start_time,
        ):
            if node.observation_type == "TRACE":
                continue
            entries.append(
                TimelineEntry(
                    stage=node.name,
                    status=node.metadata.get("status", "unknown"),
                    started_at=node.start_time,
                    ended_at=node.end_time,
                    duration_ms=node.metadata.get("duration_ms"),
                    node=node.node,
                    step=node.step,
                )
            )
        entries.sort(key=lambda item: item.started_at)
        return [asdict(entry) for entry in entries]

    def get_user_insights(self, *, user_ids: list[str] | None = None) -> list[dict[str, Any]]:
        return serialize_user_metrics(self._repository.get_user_metrics(user_ids=user_ids))

    def get_provider_metrics(self, *, trace_id: str | None = None) -> list[dict[str, Any]]:
        return serialize_provider_metrics(self._repository.get_provider_metrics(trace_id=trace_id))

    def get_replay_view(self, *, trace_id: str) -> list[dict[str, Any]]:
        return serialize_replay_records(self._repository.get_replay_records(trace_id=trace_id))

    def build_alerts(
        self,
        *,
        trace_id: str | None = None,
        queue_depth: int = 0,
        dropped_events: int = 0,
        thresholds: AlertThresholds | None = None,
    ) -> list[dict[str, Any]]:
        limits = thresholds or AlertThresholds()
        alerts: list[AlertRecord] = []

        provider_metrics = self._repository.get_provider_metrics(trace_id=trace_id)
        total_errors = sum(metric.error_count for metric in provider_metrics)
        if total_errors > limits.max_error_count:
            alerts.append(
                AlertRecord(
                    severity="error",
                    code="provider_errors_exceeded",
                    message="Provider error count exceeded configured threshold",
                    context={"trace_id": trace_id, "error_count": total_errors},
                )
            )
        if queue_depth > limits.max_queue_depth:
            alerts.append(
                AlertRecord(
                    severity="warning",
                    code="queue_depth_exceeded",
                    message="Telemetry queue depth exceeded configured threshold",
                    context={"trace_id": trace_id, "queue_depth": queue_depth},
                )
            )
        if dropped_events > limits.max_drop_count:
            alerts.append(
                AlertRecord(
                    severity="error",
                    code="dropped_events_detected",
                    message="Telemetry events were dropped",
                    context={"trace_id": trace_id, "dropped_events": dropped_events},
                )
            )
        return [asdict(alert) for alert in alerts]


def build_graph_availability(nodes: Iterable[AgentGraphNode]) -> bool:
    materialized = list(nodes)
    if not materialized:
        return False
    has_graphable_observations = any(node.observation_type not in {"EVENT"} for node in materialized)
    has_steps = any(node.step not in (None, 0) for node in materialized)
    return has_graphable_observations or has_steps


__all__ = [
    "AlertRecord",
    "AlertThresholds",
    "ObservabilityDashboard",
    "TimelineEntry",
    "build_graph_availability",
]
