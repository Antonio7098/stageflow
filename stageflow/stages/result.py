"""Unified stage result types for substrate architecture.

This module provides the canonical result types for stage execution,
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

# Legacy StageStatus type (used by old PipelineContext.record_stage_event)
LegacyStageStatus = Literal["started", "completed", "failed"]


@dataclass(slots=True)
class StageResult:
    """Typed result returned by a stage."""

    name: str
    status: LegacyStageStatus
    started_at: datetime
    ended_at: datetime
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class StageError(Exception):
    """Raised when a stage fails."""

    def __init__(self, stage: str, original: Exception) -> None:
        super().__init__(f"Stage {stage} failed: {original}")
        self.stage = stage
        self.original = original


__all__ = [
    "StageResult",
    "StageError",
    "LegacyStageStatus",
]
