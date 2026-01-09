"""Helpers for emitting opt-in wide observability events."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from stageflow.stages.result import StageResult

try:  # pragma: no cover - typing import
    from stageflow.stages.context import PipelineContext
except Exception:  # pragma: no cover - fallback for typing
    class PipelineContext(Protocol):  # type: ignore[misc]
        pipeline_run_id: Any
        request_id: Any
        session_id: Any
        user_id: Any
        org_id: Any
        topology: str | None
        execution_mode: str | None
        service: str
        event_sink: Any


def _context_metadata(ctx: PipelineContext) -> dict[str, Any]:
    return {
        "pipeline_run_id": str(ctx.pipeline_run_id) if ctx.pipeline_run_id else None,
        "request_id": str(ctx.request_id) if ctx.request_id else None,
        "session_id": str(ctx.session_id) if ctx.session_id else None,
        "user_id": str(ctx.user_id) if ctx.user_id else None,
        "org_id": str(ctx.org_id) if ctx.org_id else None,
        "topology": ctx.topology,
        "execution_mode": ctx.execution_mode,
        "service": ctx.service,
    }


def _stage_result_summary(result: StageResult) -> dict[str, Any]:
    return {
        "stage": result.name,
        "status": result.status,
        "started_at": result.started_at.isoformat(),
        "ended_at": result.ended_at.isoformat(),
        "duration_ms": _duration_ms(result.started_at, result.ended_at),
        "error": result.error,
        "data_keys": sorted(result.data.keys()),
    }


def _duration_ms(started_at: datetime, ended_at: datetime) -> int:
    return int((ended_at - started_at).total_seconds() * 1000)


def _stage_counts(stage_results: Mapping[str, StageResult]) -> dict[str, int]:
    counts = Counter(result.status for result in stage_results.values())
    return dict(counts)


@dataclass(slots=True)
class WideEventEmitter:
    """Helper for emitting structured pipeline/stage-wide events.

    Applications can share a single emitter instance across interceptors,
    StageGraph instances, or custom orchestration layers.
    """

    stage_event_type: str = "stage.wide"
    pipeline_event_type: str = "pipeline.wide"

    def emit_stage_event(
        self,
        *,
        ctx: PipelineContext,
        result: StageResult,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Emit a wide event describing a single stage result."""
        payload = self.build_stage_payload(ctx=ctx, result=result, extra=extra)
        ctx.event_sink.try_emit(type=self.stage_event_type, data=payload)

    def emit_pipeline_event(
        self,
        *,
        ctx: PipelineContext,
        stage_results: Mapping[str, StageResult],
        pipeline_name: str | None = None,
        status: str | None = None,
        duration_ms: int | None = None,
        started_at: datetime | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Emit a wide event summarizing an entire pipeline run."""
        payload = self.build_pipeline_payload(
            ctx=ctx,
            stage_results=stage_results,
            pipeline_name=pipeline_name,
            status=status,
            duration_ms=duration_ms,
            started_at=started_at,
            extra=extra,
        )
        ctx.event_sink.try_emit(type=self.pipeline_event_type, data=payload)

    @staticmethod
    def build_stage_payload(
        *,
        ctx: PipelineContext,
        result: StageResult,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            **_context_metadata(ctx),
            **_stage_result_summary(result),
        }
        if extra:
            payload["extra"] = dict(extra)
        return payload

    @staticmethod
    def build_pipeline_payload(
        *,
        ctx: PipelineContext,
        stage_results: Mapping[str, StageResult],
        pipeline_name: str | None = None,
        status: str | None = None,
        duration_ms: int | None = None,
        started_at: datetime | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        pipeline_name = pipeline_name or ctx.topology or "pipeline"
        if duration_ms is None and started_at is not None:
            duration_ms = _duration_ms(started_at, datetime.now(UTC))

        details = [_stage_result_summary(result) for result in stage_results.values()]
        status = status or ("failed" if any(r["status"] == "failed" for r in details) else "completed")

        payload: dict[str, Any] = {
            **_context_metadata(ctx),
            "pipeline_name": pipeline_name,
            "status": status,
            "duration_ms": duration_ms,
            "stage_counts": _stage_counts(stage_results),
            "stage_details": details,
        }
        if extra:
            payload["extra"] = dict(extra)
        return payload


def emit_stage_wide_event(
    *,
    ctx: PipelineContext,
    result: StageResult,
    emitter: WideEventEmitter | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Emit a stage-wide event using the provided or default emitter."""
    (emitter or WideEventEmitter()).emit_stage_event(ctx=ctx, result=result, extra=extra)


def emit_pipeline_wide_event(
    *,
    ctx: PipelineContext,
    stage_results: Mapping[str, StageResult],
    emitter: WideEventEmitter | None = None,
    pipeline_name: str | None = None,
    status: str | None = None,
    duration_ms: int | None = None,
    started_at: datetime | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Emit a pipeline-wide event that summarizes all stage results."""
    (emitter or WideEventEmitter()).emit_pipeline_event(
        ctx=ctx,
        stage_results=stage_results,
        pipeline_name=pipeline_name,
        status=status,
        duration_ms=duration_ms,
        started_at=started_at,
        extra=extra,
    )


__all__ = [
    "WideEventEmitter",
    "emit_stage_wide_event",
    "emit_pipeline_wide_event",
]
