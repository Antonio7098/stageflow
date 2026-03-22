from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractContextManager
from typing import Any, TypeVar

from stageflow.events.sink import EventSink
from stageflow.observability.envelope import build_payload, infer_event_kind
from stageflow.observability.tracing import StageflowTracer

T = TypeVar("T")


class TelemetryExporter:
    def __init__(
        self,
        sink: EventSink,
        *,
        tracer: StageflowTracer | None = None,
        service_name: str = "stageflow.observability",
    ) -> None:
        self._sink = sink
        self._tracer = tracer or StageflowTracer(service_name)

    @property
    def sink(self) -> EventSink:
        return self._sink

    @property
    def tracer(self) -> StageflowTracer:
        return self._tracer

    async def emit(
        self,
        *,
        event_type: str,
        ctx: Any | None,
        data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._build_payload(event_type=event_type, ctx=ctx, data=data)
        await self._sink.emit(type=event_type, data=payload)
        return payload

    def emit_nowait(
        self,
        *,
        event_type: str,
        ctx: Any | None,
        data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._build_payload(event_type=event_type, ctx=ctx, data=data)
        self._sink.try_emit(type=event_type, data=payload)
        return payload

    async def instrument_async(
        self,
        *,
        span_name: str,
        event_type: str,
        ctx: Any | None,
        callback: Callable[[Any], Awaitable[T]],
        data: Mapping[str, Any] | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> T:
        with self._start_span(span_name=span_name, attributes=attributes) as span:
            payload = self._build_payload(event_type=event_type, ctx=ctx, data=data)
            self._sink.try_emit(type=event_type, data=payload)
            try:
                result = await callback(span)
            except Exception:
                if hasattr(span, "set_attribute"):
                    span.set_attribute("stageflow.observability.error", True)
                raise
            return result

    def _start_span(
        self,
        *,
        span_name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> AbstractContextManager[Any]:
        return self._tracer.start_span(span_name, attributes=dict(attributes or {}))

    def _build_payload(
        self,
        *,
        event_type: str,
        ctx: Any | None,
        data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return build_payload(
            event_type=event_type,
            ctx=ctx,
            data=data,
            event_kind=infer_event_kind(event_type),
        )


__all__ = ["TelemetryExporter"]
