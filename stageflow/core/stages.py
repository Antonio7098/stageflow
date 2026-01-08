"""Unified stage types for stageflow architecture.

This module provides the canonical types for the unified stage system:
- StageKind: Categorization of stage types
- StageStatus: Execution status outcomes
- StageOutput: Unified return type for all stages
- Stage: Protocol for all stage implementations
- StageContext: Execution context with snapshot + output buffer

Every component in the system is a Stage with a StageKind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from time import time
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from stageflow.context.snapshot import ContextSnapshot


class PipelineTimer:
    """Shared timer for consistent cross-stage timing.

    Provides a single source of truth for pipeline timing, ensuring all stages
    use the same reference point for latency calculations.

    Usage:
        timer = PipelineTimer()
        ctx = StageContext(snapshot=snapshot, config={"timer": timer})

        # In a stage:
        start_ms = ctx.timer.now_ms()
        # ... do work ...
        elapsed = ctx.timer.now_ms() - start_ms
    """

    __slots__ = ("_pipeline_start_ms",)

    def __init__(self) -> None:
        self._pipeline_start_ms: int = int(time() * 1000)

    @property
    def pipeline_start_ms(self) -> int:
        """When the pipeline started (epoch milliseconds)."""
        return self._pipeline_start_ms

    def now_ms(self) -> int:
        """Return current time in milliseconds relative to pipeline start."""
        return int(time() * 1000)

    def elapsed_ms(self) -> int:
        """Milliseconds elapsed since pipeline start."""
        return self.now_ms() - self._pipeline_start_ms

    @property
    def started_at(self) -> datetime:
        """When the pipeline started as a datetime (UTC)."""
        return datetime.fromtimestamp(self._pipeline_start_ms / 1000.0, tz=UTC)


class StageKind(str, Enum):
    """Categorization of stage types for unified registry.

    All stages belong to exactly one kind which determines their
    lifecycle, typical input/output, and behavior patterns.
    """

    TRANSFORM = "transform"  # STT, TTS, LLM - change input form
    ENRICH = "enrich"  # Profile, Memory, Skills - add context
    ROUTE = "route"  # Router, Dispatcher - select path
    GUARD = "guard"  # Guardrails, Policy - validate
    WORK = "work"  # Assessment, Triage, Persist - side effects
    AGENT = "agent"  # Coach, Interviewer - main interactor


class StageStatus(str, Enum):
    """Possible outcomes from stage execution."""

    OK = "ok"  # Stage completed successfully
    SKIP = "skip"  # Stage was skipped (conditional)
    CANCEL = "cancel"  # Pipeline cancelled (no error, just stop)
    FAIL = "fail"  # Stage failed (error)
    RETRY = "retry"  # Stage failed but is retryable


@dataclass(frozen=True, slots=True)
class StageOutput:
    """Unified return type for all stage executions.

    Every stage returns a StageOutput regardless of its kind.
    The status field indicates the outcome, and data/artifacts
    contain the results.
    """

    status: StageStatus
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[StageArtifact] = field(default_factory=list)
    events: list[StageEvent] = field(default_factory=list)
    error: str | None = None

    @classmethod
    def ok(cls, data: dict[str, Any] | None = None, **kwargs) -> StageOutput:
        """Create a successful output."""
        return cls(status=StageStatus.OK, data=data or kwargs)

    @classmethod
    def skip(cls, reason: str = "", data: dict[str, Any] | None = None) -> StageOutput:
        """Create a skipped output."""
        return cls(status=StageStatus.SKIP, data={"reason": reason, **(data or {})})

    @classmethod
    def cancel(cls, reason: str = "", data: dict[str, Any] | None = None) -> StageOutput:
        """Create a cancelled output to stop pipeline without error."""
        return cls(status=StageStatus.CANCEL, data={"cancel_reason": reason, **(data or {})})

    @classmethod
    def fail(cls, error: str, data: dict[str, Any] | None = None) -> StageOutput:
        """Create a failed output."""
        return cls(status=StageStatus.FAIL, error=error, data=data or {})

    @classmethod
    def retry(cls, error: str, data: dict[str, Any] | None = None) -> StageOutput:
        """Create a retry-needed output."""
        return cls(status=StageStatus.RETRY, error=error, data=data or {})


@dataclass(frozen=True, slots=True)
class StageArtifact:
    """An artifact produced by a stage during execution."""

    type: str  # e.g., "audio", "transcript", "assessment"
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True, slots=True)
class StageEvent:
    """An event emitted by a stage during execution."""

    type: str  # e.g., "started", "progress", "completed"
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)


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


class Stage(Protocol):
    """Protocol for all stage implementations.

    Every component in the framework system is a Stage with a
    StageKind. This includes:
    - STT, TTS, LLM stages (TRANSFORM)
    - Profile, Memory, Skills stages (ENRICH)
    - Router, Dispatcher stages (ROUTE)
    - Guardrails, Policy stages (GUARD)
    - Assessment, Triage, Persist stages (WORK)
    - Coach, Interviewer stages (AGENT)

    Each stage has:
    - name: Unique identifier within its kind
    - kind: StageKind categorization
    - execute(ctx): Core execution method
    """

    name: str
    kind: StageKind

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Execute the stage logic.

        Args:
            ctx: StageContext with snapshot and output buffer

        Returns:
            StageOutput with status, data, artifacts, and events
        """
        ...


def create_stage_context(
    snapshot: ContextSnapshot,
    config: dict[str, Any] | None = None,
) -> StageContext:
    """Factory function to create a StageContext."""
    return StageContext(snapshot=snapshot, config=config)


__all__ = [
    "StageKind",
    "StageStatus",
    "StageOutput",
    "StageArtifact",
    "StageEvent",
    "StageContext",
    "Stage",
    "PipelineTimer",
    "create_stage_context",
]
