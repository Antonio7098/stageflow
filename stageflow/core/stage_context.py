"""Stage execution context.

StageContext is the per-stage execution wrapper that implements the
ExecutionContext protocol. It wraps an immutable ContextSnapshot with
a mutable output buffer and optional event sink for observability.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from .stage_enums import StageStatus
from .stage_output import StageArtifact, StageEvent, StageOutput
from .timer import PipelineTimer

if TYPE_CHECKING:
    from stageflow.context import ContextSnapshot
    from stageflow.protocols import EventSink

logger = logging.getLogger("stageflow.core.stage_context")


class StageContext:
    """Execution context for stages.

    Wraps an immutable ContextSnapshot with a mutable output buffer.
    Stages receive StageContext and emit outputs through it.

    The snapshot is frozen - stages cannot modify input context.
    All outputs go through the append-only output buffer.
    
    Implements the ExecutionContext protocol for compatibility with
    tools and other components that need a common context interface.
    """

    __slots__ = ("_snapshot", "_outputs", "_config", "_started_at", "_event_sink")

    def __init__(
        self,
        snapshot: ContextSnapshot,
        config: dict[str, Any] | None = None,
    ) -> None:
        config = config or {}
        object.__setattr__(self, "_snapshot", snapshot)
        object.__setattr__(self, "_outputs", [])
        object.__setattr__(self, "_config", config)
        object.__setattr__(self, "_started_at", datetime.utcnow())
        # Extract event_sink from config for ExecutionContext protocol
        object.__setattr__(self, "_event_sink", config.get("event_sink"))

    @property
    def snapshot(self) -> ContextSnapshot:
        """Immutable input snapshot (read-only)."""
        return self._snapshot

    @property
    def config(self) -> dict[str, Any]:
        """Stage configuration (read-only)."""
        return self._config

    @property
    def started_at(self) -> datetime:
        """When this context was created."""
        return self._started_at

    # === ExecutionContext protocol implementation ===
    
    @property
    def pipeline_run_id(self) -> UUID | None:
        """Pipeline run identifier for correlation (from snapshot)."""
        return self._snapshot.pipeline_run_id
    
    @property
    def request_id(self) -> UUID | None:
        """Request identifier for tracing (from snapshot)."""
        return self._snapshot.request_id
    
    @property
    def execution_mode(self) -> str | None:
        """Current execution mode (from snapshot)."""
        return self._snapshot.execution_mode
    
    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for serialization.
        
        Combines snapshot data with context metadata for tool execution
        and serialization purposes.
        
        Returns:
            Dictionary representation of the context
        """
        result = self._snapshot.to_dict()
        result["started_at"] = self._started_at.isoformat()
        # Include stage-specific config (excluding non-serializable items)
        serializable_config = {
            k: v for k, v in self._config.items()
            if k not in ("event_sink", "timer", "inputs")
        }
        if serializable_config:
            result["stage_config"] = serializable_config
        return result
    
    def try_emit_event(self, type: str, data: dict[str, Any]) -> None:
        """Emit an event without blocking (fire-and-forget).
        
        If an event sink is available in config, emits through it.
        Otherwise logs the event at debug level.
        
        Args:
            type: Event type string (e.g., "tool.completed")
            data: Event payload data
        """
        # Add correlation IDs to event data
        enriched_data = {
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "request_id": str(self.request_id) if self.request_id else None,
            "execution_mode": self.execution_mode,
            **data,
        }
        
        if self._event_sink is not None:
            try:
                self._event_sink.try_emit(type=type, data=enriched_data)
            except Exception as e:
                logger.warning(f"Failed to emit event {type}: {e}")
        else:
            logger.debug(f"Event (no sink): {type}", extra=enriched_data)

    # === End ExecutionContext protocol ===

    @property
    def timer(self) -> PipelineTimer:
        """Shared pipeline timer for consistent cross-stage timing.

        If a timer was provided in the config, returns it. Otherwise returns
        a new timer initialized to this context's started_at time.
        """
        timer = self._config.get("timer")
        if timer is None:
            # Create a timer initialized to this context's start time
            timer = PipelineTimer()
            # Adjust to match this context's started_at for consistency
            object.__setattr__(
                timer, "_pipeline_start_ms", int(self._started_at.timestamp() * 1000)
            )
        return timer

    @classmethod
    def now(cls) -> datetime:
        """Return current UTC timestamp for consistent stage timing.

        This method provides a centralized time source for all stages,
        ensuring timing consistency across the pipeline.
        """
        return datetime.now(UTC)

    def emit_event(self, type: str, data: dict[str, Any]) -> None:
        """Emit an event during execution."""
        self._outputs.append(
            StageOutput(status=StageStatus.OK, events=[StageEvent(type=type, data=data)])
        )

    def add_artifact(self, type: str, payload: dict[str, Any]) -> None:
        """Add an artifact to the output."""
        self._outputs.append(
            StageOutput(
                status=StageStatus.OK, artifacts=[StageArtifact(type=type, payload=payload)]
            )
        )

    def collect_outputs(self) -> list[StageOutput]:
        """Collect all outputs emitted during execution."""
        return list(self._outputs)

    def get_output_data(self, key: str, default: Any = None) -> Any:
        """Get a value from any output data."""
        for output in self._outputs:
            if key in output.data:
                return output.data[key]
        return default
    
    @property
    def event_sink(self) -> EventSink | None:
        """Get the event sink if available."""
        return self._event_sink


def create_stage_context(
    snapshot: ContextSnapshot,
    config: dict[str, Any] | None = None,
) -> StageContext:
    """Factory function to create a StageContext."""
    return StageContext(snapshot=snapshot, config=config)
