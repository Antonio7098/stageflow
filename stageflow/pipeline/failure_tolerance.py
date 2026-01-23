"""Failure tolerance utilities for DAG execution.

Provides continue-on-failure mode that records failures but continues
executing unrelated branches, and backpressure management for burst loads.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger("stageflow.pipeline.failure_tolerance")


class FailureMode(Enum):
    """How to handle stage failures."""

    FAIL_FAST = auto()  # Default: stop pipeline on first failure
    CONTINUE_ON_FAILURE = auto()  # Record failure, continue unrelated branches
    BEST_EFFORT = auto()  # Continue all branches, collect all failures


@dataclass
class FailureRecord:
    """Record of a stage failure."""

    stage: str
    error: str
    error_type: str
    recoverable: bool
    timestamp: float = field(default_factory=time.time)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class FailureSummary:
    """Summary of failures during pipeline execution."""

    total_stages: int
    completed_stages: int
    failed_stages: int
    failures: list[FailureRecord]
    partial_results: dict[str, Any]

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_stages == 0:
            return 0.0
        return self.completed_stages / self.total_stages

    @property
    def has_failures(self) -> bool:
        """Check if any failures occurred."""
        return len(self.failures) > 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_stages": self.total_stages,
            "completed_stages": self.completed_stages,
            "failed_stages": self.failed_stages,
            "success_rate": self.success_rate,
            "failures": [
                {
                    "stage": f.stage,
                    "error": f.error,
                    "error_type": f.error_type,
                    "recoverable": f.recoverable,
                    "timestamp": f.timestamp,
                }
                for f in self.failures
            ],
        }


class FailureCollector:
    """Collect and manage failures during pipeline execution."""

    def __init__(self, mode: FailureMode = FailureMode.FAIL_FAST) -> None:
        self.mode = mode
        self._failures: list[FailureRecord] = []
        self._failed_stages: set[str] = set()
        self._completed_stages: set[str] = set()

    def record_failure(
        self,
        stage: str,
        error: Exception | str,
        recoverable: bool = False,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record a stage failure."""
        error_str = str(error)
        error_type = type(error).__name__ if isinstance(error, Exception) else "Error"

        record = FailureRecord(
            stage=stage,
            error=error_str,
            error_type=error_type,
            recoverable=recoverable,
            context=context or {},
        )

        self._failures.append(record)
        self._failed_stages.add(stage)

        logger.warning(
            f"Stage failure recorded: {stage}",
            extra={
                "event": "failure_recorded",
                "stage": stage,
                "error": error_str,
                "error_type": error_type,
                "recoverable": recoverable,
                "mode": self.mode.name,
            },
        )

    def record_completion(self, stage: str) -> None:
        """Record a stage completion."""
        self._completed_stages.add(stage)

    def should_continue(self, _stage: str, dependent_on: set[str]) -> bool:
        """Check if stage should be executed given failures.

        Args:
            _stage: Stage name to check (unused)
            dependent_on: Set of stages this stage depends on

        Returns:
            True if stage should execute, False if it should be skipped
        """
        if self.mode == FailureMode.FAIL_FAST:
            return len(self._failures) == 0

        if self.mode == FailureMode.CONTINUE_ON_FAILURE:
            # Skip if any dependency failed
            return not bool(dependent_on & self._failed_stages)

        # BEST_EFFORT: always try
        return True

    def get_summary(self, total_stages: int, partial_results: dict[str, Any]) -> FailureSummary:
        """Get failure summary."""
        return FailureSummary(
            total_stages=total_stages,
            completed_stages=len(self._completed_stages),
            failed_stages=len(self._failed_stages),
            failures=list(self._failures),
            partial_results=partial_results,
        )

    @property
    def has_failures(self) -> bool:
        """Check if any failures have been recorded."""
        return len(self._failures) > 0

    @property
    def failed_stages(self) -> set[str]:
        """Get set of failed stage names."""
        return self._failed_stages.copy()


@dataclass
class BackpressureConfig:
    """Configuration for backpressure management."""

    max_active_stages: int = 10  # Maximum concurrent stage executions
    high_watermark: float = 0.8  # Pause scheduling at this utilization
    low_watermark: float = 0.3  # Resume scheduling at this utilization
    latency_threshold_ms: int = 5000  # P95 latency threshold for shedding
    queue_size_limit: int = 100  # Maximum queued stages
    shed_on_overload: bool = False  # Whether to shed load when overloaded


class BackpressureMonitor:
    """Monitor and manage backpressure during DAG execution."""

    def __init__(self, config: BackpressureConfig | None = None) -> None:
        self.config = config or BackpressureConfig()
        self._semaphore = asyncio.Semaphore(self.config.max_active_stages)
        self._active_count = 0
        self._queued_count = 0
        self._latencies: list[float] = []
        self._paused = False
        self._shed_count = 0

    @property
    def utilization(self) -> float:
        """Current utilization (0-1)."""
        return self._active_count / self.config.max_active_stages

    @property
    def is_overloaded(self) -> bool:
        """Check if system is overloaded."""
        return (
            self.utilization >= self.config.high_watermark
            or self._queued_count >= self.config.queue_size_limit
            or (self._latencies and self._get_p95_latency() > self.config.latency_threshold_ms)
        )

    def _get_p95_latency(self) -> float:
        """Get P95 latency from recent samples."""
        if not self._latencies:
            return 0.0
        sorted_latencies = sorted(self._latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    async def acquire(self) -> bool:
        """Acquire permission to execute a stage.

        Returns:
            True if permission granted, False if load should be shed
        """
        self._queued_count += 1

        try:
            # Check if we should shed load
            if self.config.shed_on_overload and self.is_overloaded:
                self._shed_count += 1
                logger.warning(
                    "Shedding load due to backpressure",
                    extra={
                        "event": "load_shed",
                        "utilization": self.utilization,
                        "queued": self._queued_count,
                        "shed_count": self._shed_count,
                    },
                )
                return False

            # Wait for semaphore
            await self._semaphore.acquire()
            self._active_count += 1
            return True

        finally:
            self._queued_count -= 1

    def release(self, latency_ms: float | None = None) -> None:
        """Release execution slot and record latency."""
        self._semaphore.release()
        self._active_count -= 1

        if latency_ms is not None:
            self._latencies.append(latency_ms)
            # Keep only last 1000 samples
            if len(self._latencies) > 1000:
                self._latencies = self._latencies[-1000:]

    def get_metrics(self) -> dict[str, Any]:
        """Get current backpressure metrics."""
        return {
            "active_count": self._active_count,
            "queued_count": self._queued_count,
            "utilization": self.utilization,
            "p95_latency_ms": self._get_p95_latency(),
            "shed_count": self._shed_count,
            "is_overloaded": self.is_overloaded,
        }


@dataclass
class ConditionalDependency:
    """Conditional dependency specification.

    Allows stages to be skipped based on predicates evaluated
    against upstream outputs.
    """

    stage: str
    predicate: str  # JMESPath expression or simple key check
    skip_on_false: bool = True  # Skip stage if predicate is false

    def evaluate(self, outputs: dict[str, Any]) -> bool:
        """Evaluate predicate against upstream outputs.

        Args:
            outputs: Dict of upstream stage outputs

        Returns:
            True if stage should execute, False if should skip
        """
        try:
            # Simple key check for basic cases
            if "." not in self.predicate and "[" not in self.predicate:
                # Simple key access
                parts = self.predicate.split(":")
                if len(parts) == 2:
                    stage_name, key = parts
                    if stage_name in outputs:
                        output = outputs[stage_name]
                        value = output.data.get(key) if hasattr(output, "data") else output.get(key)
                        result = bool(value)
                        return result if not self.skip_on_false else result
                return True

            # For complex expressions, try jmespath if available
            try:
                import jmespath
                result = jmespath.search(self.predicate, outputs)
                return bool(result) if not self.skip_on_false else bool(result)
            except ImportError:
                logger.warning(
                    "jmespath not available for complex predicate evaluation",
                    extra={"predicate": self.predicate},
                )
                return True

        except Exception as e:
            logger.warning(
                f"Predicate evaluation failed: {e}",
                extra={"predicate": self.predicate, "error": str(e)},
            )
            return True  # Default to executing on evaluation failure


__all__ = [
    "BackpressureConfig",
    "BackpressureMonitor",
    "ConditionalDependency",
    "FailureCollector",
    "FailureMode",
    "FailureRecord",
    "FailureSummary",
]
