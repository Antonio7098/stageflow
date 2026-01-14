"""OutputBag - Append-only output collection with version/attempt tracking.

This module provides OutputBag, a thread-safe collection for stage outputs
that tracks execution attempts and provides rich observability data.

Features:
- Thread-safe writes with asyncio.Lock
- Attempt tracking for retry scenarios
- Timestamp recording for each output
- Conditional overwrites (allow_overwrite flag)
- Rich output entries with metadata
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from stageflow.core import StageOutput


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class OutputConflictError(Exception):
    """Raised when a stage attempts to write output without allow_overwrite.

    Attributes:
        stage_name: The stage that attempted to write.
        existing_attempt: The attempt number of the existing output.
    """

    def __init__(self, stage_name: str, existing_attempt: int) -> None:
        self.stage_name = stage_name
        self.existing_attempt = existing_attempt
        super().__init__(
            f"Stage '{stage_name}' already has output (attempt {existing_attempt}). "
            f"Use allow_overwrite=True for retry scenarios."
        )


@dataclass(frozen=True, slots=True)
class OutputEntry:
    """A single output entry with metadata.

    Captures a stage's output along with timing and attempt information
    for observability and debugging.

    Attributes:
        output: The StageOutput produced by the stage.
        attempt: Which execution attempt this is (1-indexed).
        timestamp: When this output was recorded.
        stage_name: Name of the stage that produced this output.
    """

    output: StageOutput
    attempt: int
    timestamp: datetime
    stage_name: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "stage_name": self.stage_name,
            "attempt": self.attempt,
            "timestamp": self.timestamp.isoformat(),
            "status": self.output.status.value,
            "data": self.output.data,
            "error": self.output.error,
            "duration_ms": self.output.duration_ms,
            "artifacts_count": len(self.output.artifacts),
            "events_count": len(self.output.events),
        }


class OutputBag:
    """Thread-safe, append-only collection of stage outputs with attempt tracking.

    OutputBag is the central collection point for stage outputs during
    pipeline execution. It provides:

    1. **Thread Safety**: Async lock protects concurrent writes
    2. **Attempt Tracking**: Records which attempt produced each output
    3. **Conditional Overwrites**: Default strict, opt-in for retries
    4. **Rich Metadata**: Timestamps and attempt numbers for observability

    Example:
        bag = OutputBag()

        # Normal write
        await bag.write("stt_stage", stt_output)

        # Retry scenario - overwrite previous
        await bag.write("stt_stage", retry_output, allow_overwrite=True)

        # Access outputs
        stt_entry = bag.get("stt_stage")
        print(f"Attempt {stt_entry.attempt}: {stt_entry.output.status}")
    """

    def __init__(self) -> None:
        """Initialize an empty OutputBag."""
        self._entries: dict[str, OutputEntry] = {}
        self._lock = asyncio.Lock()

    async def write(
        self,
        stage_name: str,
        output: StageOutput,
        *,
        allow_overwrite: bool = False,
    ) -> OutputEntry:
        """Write a stage output to the bag.

        Args:
            stage_name: Name of the stage producing the output.
            output: The StageOutput to store.
            allow_overwrite: If True, allows overwriting existing output
                (for retry scenarios). Increments attempt counter.

        Returns:
            The OutputEntry that was created.

        Raises:
            OutputConflictError: If stage already has output and
                allow_overwrite is False.
        """
        async with self._lock:
            existing = self._entries.get(stage_name)

            if existing is not None and not allow_overwrite:
                raise OutputConflictError(stage_name, existing.attempt)

            attempt = (existing.attempt + 1) if existing else 1

            entry = OutputEntry(
                output=output,
                attempt=attempt,
                timestamp=_utc_now(),
                stage_name=stage_name,
            )
            self._entries[stage_name] = entry
            return entry

    def write_sync(
        self,
        stage_name: str,
        output: StageOutput,
        *,
        allow_overwrite: bool = False,
    ) -> OutputEntry:
        """Synchronous version of write for non-async contexts.

        Warning: Not thread-safe. Only use when you know there are no
        concurrent writes (e.g., single-threaded test setup).

        Args:
            stage_name: Name of the stage producing the output.
            output: The StageOutput to store.
            allow_overwrite: If True, allows overwriting existing output.

        Returns:
            The OutputEntry that was created.

        Raises:
            OutputConflictError: If stage already has output and
                allow_overwrite is False.
        """
        existing = self._entries.get(stage_name)

        if existing is not None and not allow_overwrite:
            raise OutputConflictError(stage_name, existing.attempt)

        attempt = (existing.attempt + 1) if existing else 1

        entry = OutputEntry(
            output=output,
            attempt=attempt,
            timestamp=_utc_now(),
            stage_name=stage_name,
        )
        self._entries[stage_name] = entry
        return entry

    def get(self, stage_name: str) -> OutputEntry | None:
        """Get the output entry for a stage.

        Args:
            stage_name: Name of the stage.

        Returns:
            OutputEntry if found, None otherwise.
        """
        return self._entries.get(stage_name)

    def get_output(self, stage_name: str) -> StageOutput | None:
        """Get just the StageOutput for a stage.

        Convenience method that extracts the output from the entry.

        Args:
            stage_name: Name of the stage.

        Returns:
            StageOutput if found, None otherwise.
        """
        entry = self._entries.get(stage_name)
        return entry.output if entry else None

    def get_value(
        self,
        stage_name: str,
        key: str,
        default: Any = None,
    ) -> Any:
        """Get a specific value from a stage's output data.

        Args:
            stage_name: Name of the stage.
            key: Key to look up in output.data.
            default: Value to return if not found.

        Returns:
            The value from output.data, or default.
        """
        entry = self._entries.get(stage_name)
        if entry is None:
            return default
        return entry.output.data.get(key, default)

    def has(self, stage_name: str) -> bool:
        """Check if a stage has written output.

        Args:
            stage_name: Name of the stage.

        Returns:
            True if stage has output, False otherwise.
        """
        return stage_name in self._entries

    def keys(self) -> list[str]:
        """Get all stage names that have written output.

        Returns:
            List of stage names in insertion order.
        """
        return list(self._entries.keys())

    def entries(self) -> list[OutputEntry]:
        """Get all output entries.

        Returns:
            List of OutputEntry in insertion order.
        """
        return list(self._entries.values())

    def outputs(self) -> dict[str, StageOutput]:
        """Get all outputs as a dict (without entry metadata).

        Useful for passing to StageInputs.prior_outputs.

        Returns:
            Dict mapping stage names to their StageOutput.
        """
        return {name: entry.output for name, entry in self._entries.items()}

    def to_dict(self) -> dict[str, Any]:
        """Convert bag to JSON-serializable dictionary.

        Returns:
            Dict with all entries serialized.
        """
        return {
            "entries": {
                name: entry.to_dict()
                for name, entry in self._entries.items()
            },
            "stage_count": len(self._entries),
            "total_attempts": sum(e.attempt for e in self._entries.values()),
        }

    def get_attempt_count(self, stage_name: str) -> int:
        """Get the attempt count for a stage.

        Args:
            stage_name: Name of the stage.

        Returns:
            Number of attempts (0 if no output).
        """
        entry = self._entries.get(stage_name)
        return entry.attempt if entry else 0

    def get_retry_stages(self) -> list[str]:
        """Get names of stages that have been retried.

        Returns:
            List of stage names with attempt > 1.
        """
        return [
            name
            for name, entry in self._entries.items()
            if entry.attempt > 1
        ]

    def __contains__(self, stage_name: str) -> bool:
        """Check if stage has output (for 'in' operator)."""
        return stage_name in self._entries

    def __len__(self) -> int:
        """Get number of stages with output."""
        return len(self._entries)

    def __repr__(self) -> str:
        """String representation for debugging."""
        stages = list(self._entries.keys())
        return f"OutputBag(stages={stages})"


__all__ = [
    "OutputBag",
    "OutputEntry",
    "OutputConflictError",
]
