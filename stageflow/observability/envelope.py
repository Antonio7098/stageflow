from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from stageflow.observability.taxonomy import EVENT_VERSION, EventKind
from stageflow.observability.tracing import get_trace_context_dict

_RESERVED_FIELDS = frozenset(
    {
        "correlation_id",
        "event_kind",
        "event_name",
        "event_version",
        "execution_mode",
        "interaction_id",
        "metadata",
        "org_id",
        "parent_run_id",
        "parent_span_id",
        "parent_stage_id",
        "pipeline_run_id",
        "request_id",
        "service",
        "session_id",
        "span_id",
        "timestamp",
        "pipeline_name",
        "trace_id",
        "user_id",
    }
)


def _stringify(value: Any) -> str | None:
    return str(value) if value is not None else None


def infer_event_kind(event_type: str) -> EventKind:
    prefix = event_type.split(".", 1)[0].strip().lower()
    mapping = {
        "agent": EventKind.AGENT,
        "approval": EventKind.TOOL,
        "evaluator": EventKind.EVALUATOR,
        "generation": EventKind.GENERATION,
        "pipeline": EventKind.TRACE,
        "score": EventKind.EVALUATOR,
        "span": EventKind.SPAN,
        "stage": EventKind.SPAN,
        "tool": EventKind.TOOL,
        "trace": EventKind.TRACE,
    }
    return mapping.get(prefix, EventKind.AGENT)


def _context_dict(ctx: Any | None) -> dict[str, Any]:
    if ctx is None or not hasattr(ctx, "to_dict"):
        return {}
    raw = ctx.to_dict()
    return raw if isinstance(raw, dict) else {}


def build_metadata(
    *,
    event_type: str,
    ctx: Any | None = None,
    event_kind: EventKind | None = None,
    timestamp: str | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context_data = _context_dict(ctx)
    trace_context = get_trace_context_dict()
    metadata = context_data.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    if extra_metadata:
        metadata = {**metadata, **dict(extra_metadata)}

    return {
        "event_version": EVENT_VERSION,
        "event_kind": (event_kind or infer_event_kind(event_type)).value,
        "event_name": event_type,
        "timestamp": timestamp or datetime.now(UTC).isoformat(),
        "pipeline_run_id": _stringify(getattr(ctx, "pipeline_run_id", context_data.get("pipeline_run_id"))),
        "parent_run_id": _stringify(getattr(ctx, "parent_run_id", context_data.get("parent_run_id"))),
        "parent_stage_id": getattr(ctx, "parent_stage_id", context_data.get("parent_stage_id")),
        "request_id": _stringify(getattr(ctx, "request_id", context_data.get("request_id"))),
        "session_id": _stringify(getattr(ctx, "session_id", context_data.get("session_id"))),
        "user_id": _stringify(getattr(ctx, "user_id", context_data.get("user_id"))),
        "org_id": _stringify(getattr(ctx, "org_id", context_data.get("org_id"))),
        "interaction_id": _stringify(getattr(ctx, "interaction_id", context_data.get("interaction_id"))),
        "execution_mode": getattr(ctx, "execution_mode", context_data.get("execution_mode")),
        "pipeline_name": getattr(ctx, "pipeline_name", context_data.get("pipeline_name")),
        "service": getattr(ctx, "service", context_data.get("service")),
        "trace_id": trace_context.get("trace_id"),
        "span_id": trace_context.get("span_id"),
        "parent_span_id": trace_context.get("parent_span_id"),
        "correlation_id": trace_context.get("correlation_id")
        or _stringify(getattr(ctx, "correlation_id", context_data.get("correlation_id"))),
        "metadata": metadata,
    }


def build_payload(
    *,
    event_type: str,
    ctx: Any | None = None,
    data: Mapping[str, Any] | None = None,
    event_kind: EventKind | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    body = dict(data or {})
    extra_metadata = body.pop("metadata", None)
    metadata = extra_metadata if isinstance(extra_metadata, Mapping) else None
    payload = build_metadata(
        event_type=event_type,
        ctx=ctx,
        event_kind=event_kind,
        timestamp=timestamp,
        extra_metadata=metadata,
    )
    for key, value in body.items():
        if key not in _RESERVED_FIELDS:
            payload[key] = value
    return payload


__all__ = ["build_metadata", "build_payload", "infer_event_kind"]
