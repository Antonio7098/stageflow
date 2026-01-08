"""Stage execution context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .stage_enums import StageStatus
from .stage_output import StageArtifact, StageEvent, StageOutput
from .timer import PipelineTimer

if TYPE_CHECKING:
    from stageflow.context import ContextSnapshot


class StageContext:
    """Execution context for stages.

    Wraps an immutable ContextSnapshot with a mutable output buffer.
    Stages receive StageContext and emit outputs through it.

    The snapshot is frozen - stages cannot modify input context.
    All outputs go through the append-only output buffer.
    """

    __slots__ = ("_snapshot", "_outputs", "_config", "_started_at")

    def __init__(
        self,
        snapshot: ContextSnapshot,
        config: dict[str, Any] | None = None,
    ) -> None:
        object.__setattr__(self, "_snapshot", snapshot)
        object.__setattr__(self, "_outputs", [])
        object.__setattr__(self, "_config", config or {})
        object.__setattr__(self, "_started_at", datetime.utcnow())

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


def create_stage_context(
    snapshot: ContextSnapshot,
    config: dict[str, Any] | None = None,
) -> StageContext:
    """Factory function to create a StageContext."""
    return StageContext(snapshot=snapshot, config=config)
