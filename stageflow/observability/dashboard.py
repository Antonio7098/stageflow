from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from stageflow.observability.repository import (
    AgentGraphNode,
    TelemetryEvent,
    TelemetryRepository,
    serialize_agent_graph,
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
class ProviderMetric:
    provider: str
    model_id: str | None
    call_count: int
    error_count: int


class ObservabilityDashboard:
    def __init__(self, repository: TelemetryRepository) -> None:
        self._repository = repository

    def get_agent_graph_view(self, *, trace_id: str) -> list[dict[str, Any]]:
        return serialize_agent_graph(self._repository.get_agent_graph_data(trace_id=trace_id))

    def get_pipeline_timeline(self, *, trace_id: str) -> list[dict[str, Any]]:
        entries: list[TimelineEntry] = []
        for node in self._repository.get_agent_graph_data(trace_id=trace_id):
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

    def get_user_insights(self) -> list[dict[str, Any]]:
        return serialize_user_metrics(self._repository.get_user_metrics())

    def get_provider_metrics(self) -> list[dict[str, Any]]:
        buckets: dict[tuple[str, str | None], list[TelemetryEvent]] = defaultdict(list)
        for event in self._repository.list_events():
            provider = event.metadata.get("provider")
            if not isinstance(provider, str):
                continue
            model_id = event.metadata.get("model_id")
            model_name = model_id if isinstance(model_id, str) else None
            buckets[(provider, model_name)].append(event)

        metrics: list[ProviderMetric] = []
        for (provider, model_id), events in buckets.items():
            metrics.append(
                ProviderMetric(
                    provider=provider,
                    model_id=model_id,
                    call_count=len(events),
                    error_count=sum(1 for event in events if "failed" in event.event_name),
                )
            )
        metrics.sort(key=lambda item: (item.provider, item.model_id or ""))
        return [asdict(metric) for metric in metrics]


def build_graph_availability(nodes: Iterable[AgentGraphNode]) -> bool:
    materialized = list(nodes)
    if not materialized:
        return False
    has_graphable_observations = any(node.observation_type not in {"EVENT"} for node in materialized)
    has_steps = any(node.step not in (None, 0) for node in materialized)
    return has_graphable_observations or has_steps


__all__ = ["ObservabilityDashboard", "TimelineEntry", "ProviderMetric", "build_graph_availability"]
