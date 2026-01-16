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

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from .timer import PipelineTimer

if TYPE_CHECKING:
    from stageflow.context import ContextSnapshot
    from stageflow.protocols import EventSink
    from stageflow.stages.context import PipelineContext
    from stageflow.stages.inputs import StageInputs

logger = logging.getLogger("stageflow.core.stage_context")


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

        from stageflow.stages.context import PipelineContext

        kwargs: dict[str, Any] = {}
        if self.event_sink is not None:
            kwargs["event_sink"] = self.event_sink

        return PipelineContext(
            pipeline_run_id=self.snapshot.pipeline_run_id,
            request_id=self.snapshot.request_id,
            session_id=self.snapshot.session_id,
            user_id=self.snapshot.user_id,
            org_id=self.snapshot.org_id,
            interaction_id=self.snapshot.interaction_id,
            topology=self.snapshot.topology,
            configuration=configuration.copy() if configuration else {},
            execution_mode=self.snapshot.execution_mode,
            service=service or "pipeline",
            data=(data.copy() if data else {}),
            db=db,
            **kwargs,
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
