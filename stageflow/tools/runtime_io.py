"""Runtime I/O helpers for tools that need updates or subpipelines."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Callable, Protocol
from uuid import UUID, uuid4

from .lifecycle import ToolLifecycleEvent, ToolLifecycleSink
from stageflow.pipeline.registry import pipeline_registry

if TYPE_CHECKING:
    from stageflow.core import StageContext
    from stageflow.pipeline.subpipeline import SubpipelineSpawner
    from stageflow.stages.context import PipelineContext

logger = logging.getLogger("stageflow.tools.runtime_io")


class ToolRuntimeIOError(RuntimeError):
    """Raised when tool runtime helpers cannot perform an operation."""


@dataclass(frozen=True, slots=True)
class ToolChildRun:
    """Structured child-run lineage emitted by a tool execution."""

    pipeline_name: str
    child_run_id: UUID
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "pipeline_name": self.pipeline_name,
            "child_run_id": str(self.child_run_id),
            "success": self.success,
            "duration_ms": self.duration_ms,
        }
        if self.data is not None:
            payload["data"] = self.data
        if self.error is not None:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True, slots=True)
class ToolUpdate:
    """Structured progress update emitted by a running tool."""

    payload: dict[str, Any]
    emitted_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {"payload": self.payload, "emitted_at": self.emitted_at}


class ToolRuntimeIO(Protocol):
    """Helper surface exposed to tool implementations."""

    async def publish_update(self, payload: dict[str, Any]) -> None:
        """Emit a structured update for an in-flight tool call."""

    async def spawn_subpipeline(
        self,
        *,
        pipeline_name: str,
        correlation_id: UUID | None = None,
        topology_override: str | None = None,
        execution_mode_override: str | None = None,
    ) -> ToolChildRun:
        """Execute a child pipeline and return structured lineage."""


class NullToolRuntimeIO:
    """Runtime helper that fails loudly for unsupported operations."""

    async def publish_update(self, payload: dict[str, Any]) -> None:  # noqa: ARG002
        raise ToolRuntimeIOError("Tool progress updates require a runtime-aware execution path")

    async def spawn_subpipeline(
        self,
        *,
        pipeline_name: str,  # noqa: ARG002
        correlation_id: UUID | None = None,  # noqa: ARG002
        topology_override: str | None = None,  # noqa: ARG002
        execution_mode_override: str | None = None,  # noqa: ARG002
    ) -> ToolChildRun:
        raise ToolRuntimeIOError("Subpipeline spawning requires a StageContext or PipelineContext")


class StageflowToolRuntimeIO:
    """Default runtime I/O implementation backed by Stageflow primitives."""

    def __init__(
        self,
        *,
        stage_context: Any,
        tool_name: str,
        call_id: str,
        parent_stage_id: str,
        on_update: Callable[..., None] | None = None,
        lifecycle_sink: ToolLifecycleSink | None = None,
        spawner: SubpipelineSpawner | None = None,
    ) -> None:
        self._stage_context = stage_context
        self._tool_name = tool_name
        self._call_id = call_id
        self._parent_stage_id = parent_stage_id
        self._on_update = on_update
        self._lifecycle_sink = lifecycle_sink
        self._spawner = spawner

    async def publish_update(self, payload: dict[str, Any]) -> None:
        update = ToolUpdate(payload=payload)
        event_payload = {
            "tool": self._tool_name,
            "call_id": self._call_id,
            "parent_stage_id": self._parent_stage_id,
            "status": "updated",
            "update": update.to_dict(),
        }
        _emit(self._stage_context, "tool.updated", event_payload)
        if self._lifecycle_sink is not None:
            await self._lifecycle_sink.emit(
                ToolLifecycleEvent(
                    event_type="tool.updated",
                    tool_name=self._tool_name,
                    call_id=self._call_id,
                    pipeline_run_id=_coerce_uuid_str(getattr(self._stage_context, "pipeline_run_id", None)),
                    request_id=_coerce_uuid_str(getattr(self._stage_context, "request_id", None)),
                    parent_stage_id=self._parent_stage_id,
                    payload=event_payload,
                )
            )
        if self._on_update is not None:
            self._on_update(
                stage_context=self._stage_context,
                tool_name=self._tool_name,
                call_id=self._call_id,
                payload=payload,
            )

    async def spawn_subpipeline(
        self,
        *,
        pipeline_name: str,
        correlation_id: UUID | None = None,
        topology_override: str | None = None,
        execution_mode_override: str | None = None,
    ) -> ToolChildRun:
        pipeline_context = _coerce_pipeline_context(self._stage_context)
        if pipeline_context is None:
            raise ToolRuntimeIOError(
                "Subpipeline spawning requires a StageContext or PipelineContext with pipeline identity"
            )

        correlation = correlation_id or uuid4()
        executor = _build_tool_executor(spawner=self._spawner)
        result = await executor.spawn_subpipeline(
            pipeline_name,
            pipeline_context,
            correlation,
            topology_override=topology_override,
            execution_mode_override=execution_mode_override,
        )
        child_run = ToolChildRun(
            pipeline_name=pipeline_name,
            child_run_id=result.child_run_id,
            success=result.success,
            data=result.data,
            error=result.error,
            duration_ms=result.duration_ms,
        )
        await self.publish_update(
            {
                "child_run": child_run.to_dict(),
                "pipeline_name": pipeline_name,
                "success": result.success,
            }
        )
        return child_run


def _build_tool_executor(*, spawner: SubpipelineSpawner | None) -> Any:
    from stageflow.tools.executor import ToolExecutor

    return ToolExecutor(spawner=spawner, registry=pipeline_registry)


def _coerce_pipeline_context(stage_context: Any) -> PipelineContext | None:
    from stageflow.core import StageContext
    from stageflow.stages.context import PipelineContext

    if isinstance(stage_context, PipelineContext):
        return stage_context
    if isinstance(stage_context, StageContext):
        return PipelineContext.from_snapshot(
            stage_context.snapshot,
            event_sink=stage_context.event_sink,
            ports=stage_context.inputs.ports,
            db=getattr(stage_context.inputs.ports, "db", None),
        )
    return None


def _emit(stage_context: Any, event_type: str, data: dict[str, Any]) -> None:
    if stage_context is not None and hasattr(stage_context, "try_emit_event"):
        stage_context.try_emit_event(event_type, data)
    else:
        logger.debug("Tool runtime update without stage context", extra={"event_type": event_type, **data})


def _coerce_uuid_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


__all__ = [
    "NullToolRuntimeIO",
    "StageflowToolRuntimeIO",
    "ToolChildRun",
    "ToolRuntimeIO",
    "ToolRuntimeIOError",
    "ToolUpdate",
]
