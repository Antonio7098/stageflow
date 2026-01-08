"""Pipeline timer for consistent timing across stages."""

from datetime import UTC, datetime
from time import time


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
