"""Stage execution context.

StageContext is the per-stage execution wrapper that implements the
ExecutionContext protocol. It wraps an immutable ContextSnapshot with
explicit fields for inputs, stage_name, timer, and optional event_sink.

The snapshot is frozen - stages cannot modify input context.
All outputs (events/artifacts) are returned in StageOutput from execute(),
not accumulated during execution.

Implements the ExecutionContext protocol for compatibility with
tools and other components that need a common context interface.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID
from warnings import warn

from .timer import PipelineTimer

if TYPE_CHECKING:
    from stageflow.context import ContextSnapshot
    from stageflow.protocols import EventSink
    from stageflow.stages.context import PipelineContext
    from stageflow.stages.inputs import StageInputs

logger = logging.getLogger("stageflow.core.stage_context")


class StageCancellationRequested(Exception):
    """Raised when cooperative stage cancellation has been requested."""

    def __init__(self, reason: str = "Stage execution cancelled") -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class StageContext:
    """Execution context for stages.

    Wraps an immutable ContextSnapshot with explicit fields for stage execution.
    Stages receive StageContext and return outputs through StageOutput.

    The snapshot is frozen - stages cannot modify input context.
    All outputs (events/artifacts) go in StageOutput returned from execute().

    Implements the ExecutionContext protocol for compatibility with
    tools and other components that need a common context interface.
    """

    snapshot: ContextSnapshot
    inputs: StageInputs
    stage_name: str
    timer: PipelineTimer
    event_sink: EventSink | None = None
    _cancellation_probe: Callable[[], bool] | None = None
    _cancellation_reason_provider: Callable[[], str | None] | None = None

    @property
    def pipeline_run_id(self) -> UUID | None:
        """Pipeline run identifier for correlation (from snapshot)."""
        return self.snapshot.pipeline_run_id

    @property
    def request_id(self) -> UUID | None:
        """Request identifier for tracing (from snapshot)."""
        return self.snapshot.request_id

    @property
    def execution_mode(self) -> str | None:
        """Current execution mode (from snapshot)."""
        return self.snapshot.execution_mode

    @property
    def started_at(self) -> datetime:
        """When this context's timer was initialized."""
        return self.timer.started_at

    @property
    def is_cancelled(self) -> bool:
        """Whether cancellation has been requested for this stage."""
        if self._cancellation_probe is None:
            return False
        return self._cancellation_probe()

    @property
    def cancellation_reason(self) -> str | None:
        """Human-readable cancellation reason when available."""
        if self._cancellation_reason_provider is None:
            return None
        return self._cancellation_reason_provider()

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for serialization.

        Combines snapshot data with context metadata for tool execution
        and serialization purposes.

        Returns:
            Dictionary representation of the context
        """
        result = self.snapshot.to_dict()
        result["stage_name"] = self.stage_name
        result["started_at"] = self.started_at.isoformat()
        return result

    def try_emit_event(self, type: str, data: dict[str, Any]) -> None:
        """Emit an event without blocking (fire-and-forget).

        If an event sink is available, emits through it.
        Otherwise logs the event at debug level.

        Args:
            type: Event type string (e.g., "tool.completed")
            data: Event payload data
        """
        enriched_data = {
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "request_id": str(self.request_id) if self.request_id else None,
            "execution_mode": self.execution_mode,
            **data,
        }

        if self.event_sink is not None:
            try:
                self.event_sink.try_emit(type=type, data=enriched_data)
            except Exception as e:
                logger.warning(f"Failed to emit event {type}: {e}")
        else:
            logger.debug(f"Event (no sink): {type}", extra=enriched_data)

    def emit_event(self, type: str, data: dict[str, Any]) -> None:
        """Backward-compatible alias for try_emit_event()."""
        self.try_emit_event(type=type, data=data)

    def raise_if_cancelled(self) -> None:
        """Raise when cooperative cancellation has been requested."""
        if not self.is_cancelled:
            return
        reason = self.cancellation_reason or f"Stage '{self.stage_name}' was cancelled"
        raise StageCancellationRequested(reason)

    async def cancellation_checkpoint(self) -> None:
        """Yield once and then raise if cancellation has been requested."""
        await asyncio.sleep(0)
        self.raise_if_cancelled()

    def record_stage_event(self, stage: str, status: str, **kwargs) -> None:
        """Record a stage execution event.

        This method is called by the pipeline execution engine to record
        stage lifecycle events (started, completed, failed, etc.).

        Args:
            stage: Stage name
            status: Event status (e.g., "started", "completed", "failed")
            **kwargs: Additional event data
        """
        event_data = {
            "stage": stage,
            "status": status,
            "stage_name": self.stage_name,
            **kwargs,
        }
        self.try_emit_event(f"stage.{status}", event_data)

    def as_pipeline_context(
        self,
        *,
        data: dict[str, Any] | None = None,
        configuration: dict[str, Any] | None = None,
        service: str | None = None,
        db: Any = None,
    ) -> PipelineContext:
        """Create a mutable PipelineContext derived from this StageContext.

        This helper reconstructs a PipelineContext using the immutable
        snapshot data available to the stage so that stages can call
        APIs (e.g., ToolExecutor.spawn_subpipeline) that require the
        orchestration context rather than the execution wrapper.

        Args:
            data: Optional initial data dict for the pipeline context.
            configuration: Optional configuration snapshot override.
            service: Optional service label override (defaults to "pipeline").
            db: Optional db/session handle to attach to the context.

        Returns:
            PipelineContext populated with the identifiers and metadata
            from this StageContext.
        """
        warn(
            "StageContext.as_pipeline_context() is deprecated; pass PipelineContext at API boundaries and keep StageContext inside stage execution.",
            DeprecationWarning,
            stacklevel=2,
        )

        from stageflow.stages.context import PipelineContext

        ports = self.inputs.ports

        return PipelineContext.from_snapshot(
            self.snapshot,
            configuration=configuration.copy() if configuration else {},
            service=service or "pipeline",
            data=(data.copy() if data else {}),
            ports=ports,
            db=db if db is not None else getattr(ports, "db", None),
            event_sink=self.event_sink,
        )

    @classmethod
    def now(cls) -> datetime:
        """Return current UTC timestamp for consistent stage timing.

        This method provides a centralized time source for all stages,
        ensuring timing consistency across the pipeline.
        """
        return datetime.now(UTC)


def create_stage_context(
    snapshot: ContextSnapshot,
    inputs: StageInputs,
    stage_name: str,
    timer: PipelineTimer,
    event_sink: EventSink | None = None,
) -> StageContext:
    """Factory function to create a StageContext."""
    return StageContext(
        snapshot=snapshot,
        inputs=inputs,
        stage_name=stage_name,
        timer=timer,
        event_sink=event_sink,
    )
