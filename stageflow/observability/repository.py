from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_name: str
    event_kind: str
    event_version: str
    timestamp: str
    pipeline_run_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    org_id: str | None = None
    interaction_id: str | None = None
    execution_mode: str | None = None
    topology: str | None = None
    service: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentGraphNode:
    id: str
    parent_observation_id: str | None
    observation_type: str
    name: str
    start_time: str
    end_time: str | None
    node: str | None
    step: int | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class UserMetric:
    user_id: str
    observation_count: int
    trace_count: int
    event_kinds: dict[str, int]


class TelemetryRepository(Protocol):
    def store(self, event: TelemetryEvent) -> None: ...

    def store_batch(self, events: Sequence[TelemetryEvent]) -> int: ...

    def list_events(self, *, event_name: str | None = None) -> list[TelemetryEvent]: ...

    def get_agent_graph_data(self, *, trace_id: str) -> list[AgentGraphNode]: ...

    def get_user_metrics(self) -> list[UserMetric]: ...


class InMemoryTelemetryRepository:
    def __init__(self) -> None:
        self._events: list[TelemetryEvent] = []

    def store(self, event: TelemetryEvent) -> None:
        self._events.append(event)

    def store_batch(self, events: Sequence[TelemetryEvent]) -> int:
        self._events.extend(events)
        return len(events)

    def list_events(self, *, event_name: str | None = None) -> list[TelemetryEvent]:
        if event_name is None:
            return list(self._events)
        return [event for event in self._events if event.event_name == event_name]

    def get_agent_graph_data(self, *, trace_id: str) -> list[AgentGraphNode]:
        nodes: list[AgentGraphNode] = []
        for event in self._events:
            payload = event.model_dump()
            event_trace_id = payload.get("trace_id") or payload.get("pipeline_run_id")
            if event_trace_id != trace_id:
                continue
            observation_id = payload.get("id")
            start_time = payload.get("start_time") or payload.get("timestamp")
            if not isinstance(observation_id, str) or not isinstance(start_time, str):
                continue
            step = payload.get("step")
            if step is not None:
                step = int(step)
            node = AgentGraphNode(
                id=observation_id,
                parent_observation_id=payload.get("parent_observation_id"),
                observation_type=str(payload.get("type") or event.event_kind).upper(),
                name=str(payload.get("name") or event.event_name),
                start_time=start_time,
                end_time=payload.get("end_time"),
                node=payload.get("node"),
                step=step,
                metadata=dict(payload.get("metadata") or {}),
            )
            nodes.append(node)
        nodes.sort(key=lambda item: datetime.fromisoformat(item.start_time))
        return nodes

    def get_user_metrics(self) -> list[UserMetric]:
        grouped: dict[str, list[TelemetryEvent]] = defaultdict(list)
        for event in self._events:
            if event.user_id is not None:
                grouped[event.user_id].append(event)

        metrics: list[UserMetric] = []
        for user_id, events in grouped.items():
            event_kinds: dict[str, int] = defaultdict(int)
            traces: set[str] = set()
            for event in events:
                event_kinds[event.event_kind] += 1
                trace_id = event.trace_id or event.pipeline_run_id
                if trace_id is not None:
                    traces.add(trace_id)
            metrics.append(
                UserMetric(
                    user_id=user_id,
                    observation_count=len(events),
                    trace_count=len(traces),
                    event_kinds=dict(event_kinds),
                )
            )
        metrics.sort(key=lambda item: item.user_id)
        return metrics


def serialize_agent_graph(nodes: Iterable[AgentGraphNode]) -> list[dict[str, Any]]:
    return [asdict(node) for node in nodes]


def serialize_user_metrics(metrics: Iterable[UserMetric]) -> list[dict[str, Any]]:
    return [asdict(metric) for metric in metrics]


__all__ = [
    "AgentGraphNode",
    "InMemoryTelemetryRepository",
    "TelemetryEvent",
    "TelemetryRepository",
    "UserMetric",
    "serialize_agent_graph",
    "serialize_user_metrics",
]
