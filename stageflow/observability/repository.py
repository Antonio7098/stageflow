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
    id: str | None = None
    pipeline_run_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    parent_observation_id: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    org_id: str | None = None
    interaction_id: str | None = None
    execution_mode: str | None = None
    pipeline_name: str | None = None
    service: str | None = None
    correlation_id: str | None = None
    type: str | None = None
    name: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    node: str | None = None
    step: int | None = None
    status: str | None = None
    duration_ms: int | float | None = None
    error_message: str | None = None
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
    session_count: int
    error_count: int
    first_event_at: str | None
    last_event_at: str | None
    total_cost: float
    event_kinds: dict[str, int]


@dataclass(frozen=True, slots=True)
class ProviderMetric:
    provider: str
    model_id: str | None
    call_count: int
    error_count: int
    total_duration_ms: float
    total_cost: float
    last_event_at: str | None


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    trace_id: str
    pipeline_run_id: str | None
    event_name: str
    timestamp: str
    payload: dict[str, Any]


class TelemetryRepository(Protocol):
    def store(self, event: TelemetryEvent) -> None: ...

    def store_batch(self, events: Sequence[TelemetryEvent]) -> int: ...

    def list_events(
        self,
        *,
        event_name: str | None = None,
        trace_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        event_kind: str | None = None,
    ) -> list[TelemetryEvent]: ...

    def get_agent_graph_data(
        self,
        *,
        trace_id: str,
        min_start_time: str | None = None,
        max_start_time: str | None = None,
    ) -> list[AgentGraphNode]: ...

    def get_user_metrics(self, *, user_ids: Sequence[str] | None = None) -> list[UserMetric]: ...

    def get_provider_metrics(self, *, trace_id: str | None = None) -> list[ProviderMetric]: ...

    def get_replay_records(self, *, trace_id: str) -> list[ReplayRecord]: ...


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _event_trace_id(event: TelemetryEvent) -> str | None:
    return event.trace_id or event.pipeline_run_id


def _event_payload(event: TelemetryEvent) -> dict[str, Any]:
    return event.model_dump()


def _metadata_number(metadata: dict[str, Any], key: str) -> float:
    value = metadata.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


class InMemoryTelemetryRepository:
    def __init__(self) -> None:
        self._events: list[TelemetryEvent] = []

    def store(self, event: TelemetryEvent) -> None:
        self._events.append(event)

    def store_batch(self, events: Sequence[TelemetryEvent]) -> int:
        self._events.extend(events)
        return len(events)

    def list_events(
        self,
        *,
        event_name: str | None = None,
        trace_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        event_kind: str | None = None,
    ) -> list[TelemetryEvent]:
        events = list(self._events)
        if event_name is not None:
            events = [event for event in events if event.event_name == event_name]
        if trace_id is not None:
            events = [event for event in events if _event_trace_id(event) == trace_id]
        if user_id is not None:
            events = [event for event in events if event.user_id == user_id]
        if session_id is not None:
            events = [event for event in events if event.session_id == session_id]
        if event_kind is not None:
            events = [event for event in events if event.event_kind == event_kind]
        return events

    def get_agent_graph_data(
        self,
        *,
        trace_id: str,
        min_start_time: str | None = None,
        max_start_time: str | None = None,
    ) -> list[AgentGraphNode]:
        nodes: list[AgentGraphNode] = []
        min_dt = _parse_timestamp(min_start_time)
        max_dt = _parse_timestamp(max_start_time)
        for event in self._events:
            payload = _event_payload(event)
            if _event_trace_id(event) != trace_id:
                continue
            start_time = payload.get("start_time") or payload.get("timestamp")
            start_dt = _parse_timestamp(start_time if isinstance(start_time, str) else None)
            if min_dt is not None and (start_dt is None or start_dt < min_dt):
                continue
            if max_dt is not None and (start_dt is None or start_dt > max_dt):
                continue
            observation_id = payload.get("id") or payload.get("span_id") or payload.get("pipeline_run_id")
            if not isinstance(observation_id, str) or not isinstance(start_time, str):
                continue
            step = payload.get("step")
            if step is not None:
                step = int(step)
            node = AgentGraphNode(
                id=observation_id,
                parent_observation_id=payload.get("parent_observation_id") or payload.get("parent_span_id"),
                observation_type=str(payload.get("type") or event.event_kind).upper(),
                name=str(payload.get("name") or event.event_name),
                start_time=start_time,
                end_time=payload.get("end_time"),
                node=payload.get("node"),
                step=step,
                metadata=dict(payload.get("metadata") or {}),
            )
            # Deduplicate by id - keep first occurrence
            if not any(n.id == observation_id for n in nodes):
                nodes.append(node)
        nodes.sort(key=lambda item: datetime.fromisoformat(item.start_time))
        return nodes

    def get_user_metrics(self, *, user_ids: Sequence[str] | None = None) -> list[UserMetric]:
        grouped: dict[str, list[TelemetryEvent]] = defaultdict(list)
        for event in self._events:
            if event.user_id is not None and (user_ids is None or event.user_id in user_ids):
                grouped[event.user_id].append(event)

        metrics: list[UserMetric] = []
        for user_id, events in grouped.items():
            event_kinds: dict[str, int] = defaultdict(int)
            traces: set[str] = set()
            sessions: set[str] = set()
            total_cost = 0.0
            error_count = 0
            timestamps = [event.timestamp for event in events]
            for event in events:
                event_kinds[event.event_kind] += 1
                trace_id = _event_trace_id(event)
                if trace_id is not None:
                    traces.add(trace_id)
                if event.session_id is not None:
                    sessions.add(event.session_id)
                if "failed" in event.event_name or event.status == "failed":
                    error_count += 1
                total_cost += _metadata_number(event.metadata, "cost")
                total_cost += _metadata_number(event.metadata, "total_cost")
            metrics.append(
                UserMetric(
                    user_id=user_id,
                    observation_count=len(events),
                    trace_count=len(traces),
                    session_count=len(sessions),
                    error_count=error_count,
                    first_event_at=min(timestamps) if timestamps else None,
                    last_event_at=max(timestamps) if timestamps else None,
                    total_cost=round(total_cost, 6),
                    event_kinds=dict(event_kinds),
                )
            )
        metrics.sort(key=lambda item: item.user_id)
        return metrics

    def get_provider_metrics(self, *, trace_id: str | None = None) -> list[ProviderMetric]:
        buckets: dict[tuple[str, str | None], list[TelemetryEvent]] = defaultdict(list)
        for event in self.list_events(trace_id=trace_id):
            provider = event.metadata.get("provider")
            if not isinstance(provider, str):
                continue
            model_id = event.metadata.get("model_id")
            buckets[(provider, model_id if isinstance(model_id, str) else None)].append(event)

        metrics: list[ProviderMetric] = []
        for (provider, model_id), events in buckets.items():
            total_duration_ms = 0.0
            total_cost = 0.0
            last_event_at: str | None = None
            error_count = 0
            for event in events:
                if isinstance(event.duration_ms, (int, float)):
                    total_duration_ms += float(event.duration_ms)
                total_duration_ms += _metadata_number(event.metadata, "duration_ms")
                total_cost += _metadata_number(event.metadata, "cost")
                total_cost += _metadata_number(event.metadata, "total_cost")
                if "failed" in event.event_name or event.status == "failed":
                    error_count += 1
                if last_event_at is None or event.timestamp > last_event_at:
                    last_event_at = event.timestamp
            metrics.append(
                ProviderMetric(
                    provider=provider,
                    model_id=model_id,
                    call_count=len(events),
                    error_count=error_count,
                    total_duration_ms=round(total_duration_ms, 3),
                    total_cost=round(total_cost, 6),
                    last_event_at=last_event_at,
                )
            )
        metrics.sort(key=lambda item: (item.provider, item.model_id or ""))
        return metrics

    def get_replay_records(self, *, trace_id: str) -> list[ReplayRecord]:
        records = [
            ReplayRecord(
                trace_id=trace_id,
                pipeline_run_id=event.pipeline_run_id,
                event_name=event.event_name,
                timestamp=event.timestamp,
                payload=_event_payload(event),
            )
            for event in self.list_events(trace_id=trace_id)
        ]
        records.sort(key=lambda item: item.timestamp)
        return records


def serialize_agent_graph(nodes: Iterable[AgentGraphNode]) -> list[dict[str, Any]]:
    return [asdict(node) for node in nodes]


def serialize_provider_metrics(metrics: Iterable[ProviderMetric]) -> list[dict[str, Any]]:
    return [asdict(metric) for metric in metrics]


def serialize_replay_records(records: Iterable[ReplayRecord]) -> list[dict[str, Any]]:
    return [asdict(record) for record in records]


def serialize_user_metrics(metrics: Iterable[UserMetric]) -> list[dict[str, Any]]:
    return [asdict(metric) for metric in metrics]


__all__ = [
    "AgentGraphNode",
    "InMemoryTelemetryRepository",
    "ProviderMetric",
    "ReplayRecord",
    "TelemetryEvent",
    "TelemetryRepository",
    "UserMetric",
    "serialize_agent_graph",
    "serialize_provider_metrics",
    "serialize_replay_records",
    "serialize_user_metrics",
]
