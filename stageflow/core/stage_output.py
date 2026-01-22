"""Stage output types for unified return values."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .stage_enums import StageStatus


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class StageArtifact:
    """An artifact produced by a stage during execution."""

    type: str  # e.g., "audio", "transcript", "assessment"
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class StageEvent:
    """An event emitted by a stage during execution."""

    type: str  # e.g., "started", "progress", "completed"
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, slots=True)
class StageOutput:
    """Unified return type for all stage executions.

    Every stage returns a StageOutput regardless of its kind.
    The status field indicates the outcome, and data/artifacts
    contain the results.

    The duration_ms field is populated by the executor after stage
    execution completes, enabling per-stage performance tracking.
    """

    status: StageStatus
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[StageArtifact] = field(default_factory=list)
    events: list[StageEvent] = field(default_factory=list)
    error: str | None = None
    duration_ms: int | None = None
    version: str | None = None

    @classmethod
    def ok(
        cls,
        data: dict[str, Any] | None = None,
        *,
        version: str | None = None,
        **kwargs,
    ) -> StageOutput:
        """Create a successful output."""
        payload = data or kwargs
        return cls(status=StageStatus.OK, data=payload, version=version)

    @classmethod
    def skip(
        cls,
        reason: str = "",
        data: dict[str, Any] | None = None,
        *,
        version: str | None = None,
    ) -> StageOutput:
        """Create a skipped output."""
        payload = {"reason": reason, **(data or {})}
        return cls(status=StageStatus.SKIP, data=payload, version=version)

    @classmethod
    def cancel(
        cls,
        reason: str = "",
        data: dict[str, Any] | None = None,
        *,
        version: str | None = None,
    ) -> StageOutput:
        """Create a cancelled output to stop pipeline without error."""
        payload = {"cancel_reason": reason, **(data or {})}
        return cls(status=StageStatus.CANCEL, data=payload, version=version)

    @classmethod
    def fail(
        cls,
        error: str | None = None,
        data: dict[str, Any] | None = None,
        *,
        response: str | None = None,
        version: str | None = None,
    ) -> StageOutput:
        """Create a failed output.

        Args:
            error: Error message describing the failure.
            data: Optional additional data about the failure.
            response: Alias for error (for API compatibility).

        Note:
            Either `error` or `response` must be provided. If both are
            provided, `error` takes precedence.
        """
        error_msg = error or response or "Unknown error"
        return cls(status=StageStatus.FAIL, error=error_msg, data=data or {}, version=version)

    @classmethod
    def retry(
        cls,
        error: str,
        data: dict[str, Any] | None = None,
        *,
        version: str | None = None,
    ) -> StageOutput:
        """Create a retry-needed output."""
        return cls(status=StageStatus.RETRY, error=error, data=data or {}, version=version)

    def with_duration(self, duration_ms: int) -> StageOutput:
        """Return a copy of this output with duration_ms set.

        Since StageOutput is frozen, this method creates a new instance
        with the duration populated. Used by executors to add timing info.

        Args:
            duration_ms: Stage execution duration in milliseconds.

        Returns:
            New StageOutput instance with duration_ms set.
        """
        return StageOutput(
            status=self.status,
            data=self.data,
            artifacts=self.artifacts,
            events=self.events,
            error=self.error,
            duration_ms=duration_ms,
            version=self.version,
        )

    def with_version(self, version: str) -> StageOutput:
        """Return a copy with an explicit schema version tag."""

        return StageOutput(
            status=self.status,
            data=self.data,
            artifacts=self.artifacts,
            events=self.events,
            error=self.error,
            duration_ms=self.duration_ms,
            version=version,
        )
