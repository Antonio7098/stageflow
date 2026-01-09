"""Subpipeline support for spawning and managing child pipeline runs.

This module provides:
- SubpipelineResult for capturing child run outcomes
- Subpipeline events for observability
- Child run tracking for cancellation propagation
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from stageflow.events import get_event_sink

if TYPE_CHECKING:
    from stageflow.stages.context import PipelineContext

logger = logging.getLogger("stageflow.subpipeline")


# Constants
DEFAULT_MAX_SUBPIPELINE_DEPTH = 5


class MaxDepthExceededError(Exception):
    """Raised when subpipeline nesting exceeds the maximum allowed depth.

    Attributes:
        current_depth: The depth at which the spawn was attempted
        max_depth: The configured maximum depth
        parent_run_id: The parent pipeline run ID
    """

    def __init__(self, current_depth: int, max_depth: int, parent_run_id: UUID | None) -> None:
        self.current_depth = current_depth
        self.max_depth = max_depth
        self.parent_run_id = parent_run_id
        super().__init__(
            f"Subpipeline depth {current_depth} exceeds maximum allowed depth {max_depth}. "
            f"Parent run: {parent_run_id}"
        )


# Subpipeline Events


@dataclass(frozen=True, slots=True)
class PipelineSpawnedChildEvent:
    """Emitted when a child pipeline is spawned."""

    parent_run_id: UUID
    child_run_id: UUID
    parent_stage_id: str
    pipeline_name: str
    correlation_id: UUID
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_run_id": str(self.parent_run_id),
            "child_run_id": str(self.child_run_id),
            "parent_stage_id": self.parent_stage_id,
            "pipeline_name": self.pipeline_name,
            "correlation_id": str(self.correlation_id),
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True, slots=True)
class PipelineChildCompletedEvent:
    """Emitted when a child pipeline completes successfully."""

    parent_run_id: UUID
    child_run_id: UUID
    pipeline_name: str
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_run_id": str(self.parent_run_id),
            "child_run_id": str(self.child_run_id),
            "pipeline_name": self.pipeline_name,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True, slots=True)
class PipelineChildFailedEvent:
    """Emitted when a child pipeline fails."""

    parent_run_id: UUID
    child_run_id: UUID
    pipeline_name: str
    error_message: str
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_run_id": str(self.parent_run_id),
            "child_run_id": str(self.child_run_id),
            "pipeline_name": self.pipeline_name,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True, slots=True)
class PipelineCanceledEvent:
    """Emitted when a pipeline is canceled."""

    pipeline_run_id: UUID
    parent_run_id: UUID | None = None
    reason: str = "user_requested"
    cascade_depth: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_run_id": str(self.pipeline_run_id),
            "parent_run_id": str(self.parent_run_id) if self.parent_run_id else None,
            "reason": self.reason,
            "cascade_depth": self.cascade_depth,
            "timestamp": self.timestamp,
        }


@dataclass
class SubpipelineResult:
    """Result from executing a subpipeline.

    Attributes:
        success: Whether the child pipeline completed successfully
        child_run_id: The child pipeline run ID
        data: Output data from the child pipeline
        error: Error message if failed
        duration_ms: Execution time in milliseconds
    """

    success: bool
    child_run_id: UUID
    data: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": self.success,
            "child_run_id": str(self.child_run_id),
            "duration_ms": self.duration_ms,
        }
        if self.data:
            result["data"] = self.data
        if self.error:
            result["error"] = self.error
        return result


class ChildRunTracker:
    """Tracks parent-child relationships for cancellation propagation.

    Thread-safe tracking of child runs for each parent, enabling
    cascading cancellation when a parent is canceled.
    """

    def __init__(self) -> None:
        self._children: dict[UUID, set[UUID]] = {}
        self._parents: dict[UUID, UUID] = {}
        self._lock = asyncio.Lock()
        self._metrics_lock = asyncio.Lock()
        # Metrics tracking
        self._registration_count = 0
        self._unregistration_count = 0
        self._lookup_count = 0
        self._tree_traversal_count = 0
        self._cleanup_count = 0
        self._max_concurrent_children = 0
        self._max_depth_seen = 0

    async def register_child(self, parent_id: UUID, child_id: UUID) -> None:
        """Register a child run under a parent.

        Args:
            parent_id: The parent pipeline run ID
            child_id: The child pipeline run ID
        """
        async with self._lock:
            if parent_id not in self._children:
                self._children[parent_id] = set()
            self._children[parent_id].add(child_id)
            self._parents[child_id] = parent_id

            # Update metrics
            current_children_count = len(self._children[parent_id])
            if current_children_count > self._max_concurrent_children:
                self._max_concurrent_children = current_children_count

        async with self._metrics_lock:
            self._registration_count += 1

    async def unregister_child(self, parent_id: UUID, child_id: UUID) -> None:
        """Unregister a child run from its parent.

        Args:
            parent_id: The parent pipeline run ID
            child_id: The child pipeline run ID
        """
        async with self._lock:
            if parent_id in self._children:
                self._children[parent_id].discard(child_id)
                if not self._children[parent_id]:
                    del self._children[parent_id]
            self._parents.pop(child_id, None)

        async with self._metrics_lock:
            self._unregistration_count += 1

    async def get_children(self, parent_id: UUID) -> set[UUID]:
        """Get all child run IDs for a parent.

        Args:
            parent_id: The parent pipeline run ID

        Returns:
            Set of child run IDs
        """
        async with self._lock:
            async with self._metrics_lock:
                self._lookup_count += 1
            return self._children.get(parent_id, set()).copy()

    async def get_parent(self, child_id: UUID) -> UUID | None:
        """Get the parent run ID for a child.

        Args:
            child_id: The child pipeline run ID

        Returns:
            Parent run ID or None if not a child
        """
        async with self._lock:
            async with self._metrics_lock:
                self._lookup_count += 1
            return self._parents.get(child_id)

    async def get_all_descendants(self, run_id: UUID) -> set[UUID]:
        """Get all descendant run IDs (children, grandchildren, etc).

        Args:
            run_id: The root run ID

        Returns:
            Set of all descendant run IDs
        """
        descendants: set[UUID] = set()
        to_process = [run_id]

        async with self._lock:
            while to_process:
                current = to_process.pop()
                children = self._children.get(current, set())
                for child in children:
                    if child not in descendants:
                        descendants.add(child)
                        to_process.append(child)

        async with self._metrics_lock:
            self._tree_traversal_count += 1

        return descendants

    async def get_root_run(self, run_id: UUID) -> UUID:
        """Get the root run ID by traversing up the parent chain.

        Args:
            run_id: Any run ID in the tree

        Returns:
            The root run ID (top-most parent)
        """
        current = run_id
        depth = 0
        async with self._lock:
            while current in self._parents:
                current = self._parents[current]
                depth += 1

        async with self._metrics_lock:
            self._lookup_count += 1
            if depth > self._max_depth_seen:
                self._max_depth_seen = depth

        return current

    async def cleanup_run(self, run_id: UUID) -> None:
        """Clean up tracking data for a completed run."""
        async with self._lock:
            # Remove from parent's children
            parent = self._parents.pop(run_id, None)
            if parent and parent in self._children:
                self._children[parent].discard(run_id)
                if not self._children[parent]:
                    del self._children[parent]
            # Remove any children tracking
            self._children.pop(run_id, None)

        async with self._metrics_lock:
            self._cleanup_count += 1

    async def get_metrics(self) -> dict[str, Any]:
        """Get current tracker metrics.

        Returns:
            Dictionary containing all tracked metrics
        """
        async with self._metrics_lock:
            return {
                "registration_count": self._registration_count,
                "unregistration_count": self._unregistration_count,
                "lookup_count": self._lookup_count,
                "tree_traversal_count": self._tree_traversal_count,
                "cleanup_count": self._cleanup_count,
                "max_concurrent_children": self._max_concurrent_children,
                "max_depth_seen": self._max_depth_seen,
                "active_parents": len(self._children),
                "active_children": len(self._parents),
                "total_relationships": self._registration_count - self._unregistration_count,
            }

    async def reset_metrics(self) -> None:
        """Reset all metrics counters to zero."""
        async with self._metrics_lock:
            self._registration_count = 0
            self._unregistration_count = 0
            self._lookup_count = 0
            self._tree_traversal_count = 0
            self._cleanup_count = 0
            self._max_concurrent_children = 0
            self._max_depth_seen = 0


# Global child run tracker
_child_tracker: ChildRunTracker | None = None


def get_child_tracker() -> ChildRunTracker:
    """Get the global child run tracker."""
    global _child_tracker
    if _child_tracker is None:
        _child_tracker = ChildRunTracker()
    return _child_tracker


def set_child_tracker(tracker: ChildRunTracker) -> None:
    """Set the global child run tracker."""
    global _child_tracker
    _child_tracker = tracker


def clear_child_tracker() -> None:
    """Clear the global child run tracker."""
    global _child_tracker
    _child_tracker = None


class SubpipelineSpawner:
    """Spawns and manages subpipeline runs.

    This class handles:
    - Creating child contexts with proper correlation
    - Tracking child runs for cancellation
    - Emitting subpipeline events
    - Cascading cancellation to children
    - Enforcing maximum nesting depth

    Attributes:
        max_depth: Maximum allowed nesting depth (default: 5)
    """

    def __init__(
        self,
        child_tracker: ChildRunTracker | None = None,
        emit_events: bool = True,
        max_depth: int = DEFAULT_MAX_SUBPIPELINE_DEPTH,
    ) -> None:
        self._tracker = child_tracker or get_child_tracker()
        self._emit_events = emit_events
        self._max_depth = max_depth
        self._canceled_runs: set[UUID] = set()
        self._lock = asyncio.Lock()
        self._run_depths: dict[UUID, int] = {}  # Track depth of each run

    @property
    def max_depth(self) -> int:
        """Maximum allowed subpipeline nesting depth."""
        return self._max_depth

    async def _get_current_depth(self, parent_run_id: UUID | None) -> int:
        """Get the current nesting depth for a parent run."""
        if parent_run_id is None:
            return 0
        async with self._lock:
            return self._run_depths.get(parent_run_id, 0)

    async def spawn(
        self,
        pipeline_name: str,
        ctx: PipelineContext,
        correlation_id: UUID,
        parent_stage_id: str,
        runner: Any,  # Pipeline runner callable
        *,
        topology: str | None = None,
        execution_mode: str | None = None,
    ) -> SubpipelineResult:
        """Spawn a child pipeline run.

        Args:
            pipeline_name: Name of the pipeline to run
            ctx: Parent context
            correlation_id: Action ID that triggered spawn
            parent_stage_id: Stage spawning the child
            runner: Async callable that executes the pipeline
            topology: Optional different topology for child
            execution_mode: Optional different execution mode

        Returns:
            SubpipelineResult with child run outcome

        Raises:
            MaxDepthExceededError: If spawning would exceed max_depth
        """
        child_run_id = uuid4()
        parent_run_id = ctx.pipeline_run_id

        # Check and enforce depth limit
        current_depth = await self._get_current_depth(parent_run_id)
        if current_depth >= self._max_depth:
            logger.error(
                f"Max subpipeline depth exceeded: {current_depth} >= {self._max_depth}",
                extra={
                    "parent_run_id": str(parent_run_id),
                    "current_depth": current_depth,
                    "max_depth": self._max_depth,
                },
            )
            raise MaxDepthExceededError(
                current_depth=current_depth,
                max_depth=self._max_depth,
                parent_run_id=parent_run_id,
            )

        # Track the new child's depth
        child_depth = current_depth + 1
        async with self._lock:
            self._run_depths[child_run_id] = child_depth

        # Create child context
        child_ctx = ctx.fork(
            child_run_id=child_run_id,
            parent_stage_id=parent_stage_id,
            correlation_id=correlation_id,
            topology=topology,
            execution_mode=execution_mode,
        )

        # Register for cancellation tracking
        if parent_run_id:
            await self._tracker.register_child(parent_run_id, child_run_id)

        # Emit spawn event
        if self._emit_events and parent_run_id:
            await self._emit_spawned(parent_run_id, child_run_id, parent_stage_id, pipeline_name, correlation_id)

        start_time = time.perf_counter()
        try:
            result = await runner(child_ctx)
            duration_ms = (time.perf_counter() - start_time) * 1000

            if self._emit_events and parent_run_id:
                await self._emit_completed(parent_run_id, child_run_id, pipeline_name, duration_ms)

            return SubpipelineResult(
                success=True,
                child_run_id=child_run_id,
                data=result if isinstance(result, dict) else {"result": result},
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Child pipeline {child_run_id} failed: {e}")

            if self._emit_events and parent_run_id:
                await self._emit_failed(parent_run_id, child_run_id, pipeline_name, str(e), duration_ms)

            return SubpipelineResult(
                success=False,
                child_run_id=child_run_id,
                error=str(e),
                duration_ms=duration_ms,
            )

        finally:
            if parent_run_id:
                await self._tracker.unregister_child(parent_run_id, child_run_id)
            # Clean up depth tracking
            async with self._lock:
                self._run_depths.pop(child_run_id, None)

    async def cancel_with_children(
        self,
        run_id: UUID,
        reason: str = "user_requested",
        contexts: dict[UUID, PipelineContext] | None = None,
    ) -> list[UUID]:
        """Cancel a run and all its children (depth-first).

        Args:
            run_id: The run to cancel
            reason: Reason for cancellation
            contexts: Optional map of run_id -> context for marking

        Returns:
            List of all canceled run IDs
        """
        canceled: list[UUID] = []

        async def cancel_recursive(current_id: UUID, depth: int) -> None:
            # Cancel children first (depth-first)
            children = await self._tracker.get_children(current_id)
            for child_id in children:
                await cancel_recursive(child_id, depth + 1)

            # Mark as canceled
            async with self._lock:
                if current_id not in self._canceled_runs:
                    self._canceled_runs.add(current_id)
                    canceled.append(current_id)

                    # Mark context if provided
                    if contexts and current_id in contexts:
                        contexts[current_id].mark_canceled()

                    # Emit cancel event
                    if self._emit_events:
                        parent = await self._tracker.get_parent(current_id)
                        await self._emit_canceled(current_id, parent, reason, depth)

        await cancel_recursive(run_id, 0)
        return canceled

    async def is_canceled(self, run_id: UUID) -> bool:
        """Check if a run has been canceled."""
        async with self._lock:
            return run_id in self._canceled_runs

    async def _emit_spawned(
        self,
        parent_run_id: UUID,
        child_run_id: UUID,
        parent_stage_id: str,
        pipeline_name: str,
        correlation_id: UUID,
    ) -> None:
        event = PipelineSpawnedChildEvent(
            parent_run_id=parent_run_id,
            child_run_id=child_run_id,
            parent_stage_id=parent_stage_id,
            pipeline_name=pipeline_name,
            correlation_id=correlation_id,
        )
        sink = get_event_sink()
        await sink.emit(type="pipeline.spawned_child", data=event.to_dict())

    async def _emit_completed(
        self,
        parent_run_id: UUID,
        child_run_id: UUID,
        pipeline_name: str,
        duration_ms: float,
    ) -> None:
        event = PipelineChildCompletedEvent(
            parent_run_id=parent_run_id,
            child_run_id=child_run_id,
            pipeline_name=pipeline_name,
            duration_ms=duration_ms,
        )
        sink = get_event_sink()
        await sink.emit(type="pipeline.child_completed", data=event.to_dict())

    async def _emit_failed(
        self,
        parent_run_id: UUID,
        child_run_id: UUID,
        pipeline_name: str,
        error_message: str,
        duration_ms: float,
    ) -> None:
        event = PipelineChildFailedEvent(
            parent_run_id=parent_run_id,
            child_run_id=child_run_id,
            pipeline_name=pipeline_name,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        sink = get_event_sink()
        await sink.emit(type="pipeline.child_failed", data=event.to_dict())

    async def _emit_canceled(
        self,
        run_id: UUID,
        parent_run_id: UUID | None,
        reason: str,
        depth: int,
    ) -> None:
        event = PipelineCanceledEvent(
            pipeline_run_id=run_id,
            parent_run_id=parent_run_id,
            reason=reason,
            cascade_depth=depth,
        )
        sink = get_event_sink()
        await sink.emit(type="pipeline.canceled", data=event.to_dict())


# Global spawner instance
_spawner: SubpipelineSpawner | None = None


def get_subpipeline_spawner() -> SubpipelineSpawner:
    """Get the global subpipeline spawner."""
    global _spawner
    if _spawner is None:
        _spawner = SubpipelineSpawner()
    return _spawner


def set_subpipeline_spawner(spawner: SubpipelineSpawner) -> None:
    """Set the global subpipeline spawner."""
    global _spawner
    _spawner = spawner


def clear_subpipeline_spawner() -> None:
    """Clear the global subpipeline spawner."""
    global _spawner
    _spawner = None


__all__ = [
    # Constants
    "DEFAULT_MAX_SUBPIPELINE_DEPTH",
    # Errors
    "MaxDepthExceededError",
    # Events
    "PipelineSpawnedChildEvent",
    "PipelineChildCompletedEvent",
    "PipelineChildFailedEvent",
    "PipelineCanceledEvent",
    # Result
    "SubpipelineResult",
    # Tracking
    "ChildRunTracker",
    "get_child_tracker",
    "set_child_tracker",
    "clear_child_tracker",
    # Spawner
    "SubpipelineSpawner",
    "get_subpipeline_spawner",
    "set_subpipeline_spawner",
    "clear_subpipeline_spawner",
]
