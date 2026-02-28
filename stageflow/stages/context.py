"""Unified PipelineContext for stageflow architecture.

This module provides the canonical execution context for pipeline stages,
including support for forking child contexts for subpipeline runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from stageflow.core import StageArtifact as Artifact
from stageflow.core import StageContext
from stageflow.events import EventSink, get_event_sink

if TYPE_CHECKING:
    from stageflow.context import ContextSnapshot
    from stageflow.context.output_bag import OutputBag
    from stageflow.core import StageContext
    from stageflow.stages.ports import AudioPorts, CorePorts, LLMPorts
    from stageflow.utils.frozen import FrozenDict


def extract_service(topology: str | None) -> str | None:
    """Extract service from topology string.

    For pipeline names like "chat_fast", returns "chat".
    For kernel names (e.g., "fast_kernel"), returns None since kernel is service-agnostic.

    Args:
        topology: The topology string (e.g., "chat_fast")

    Returns:
        Service name (e.g., "chat", "voice") or None if topology is None or is a kernel name
    """
    if topology is None:
        return None
    # Kernel names don't encode service
    if topology.endswith("_kernel"):
        return None
    # Handle pipeline names like "chat_fast", "voice_accurate"
    # Return everything before the last underscore
    parts = topology.rsplit("_", 1)
    return parts[0] if parts[0] else topology


@dataclass(slots=True, kw_only=True)
class PipelineContext:
    """Execution context shared between stages.

    Supports forking for subpipeline runs with parent-child correlation.
    Child contexts have read-only access to parent data and their own
    ContextBag for outputs.
    """

    pipeline_run_id: UUID | None
    request_id: UUID | None
    session_id: UUID | None
    user_id: UUID | None
    org_id: UUID | None
    interaction_id: UUID | None
    # Topology / Configuration / Execution Mode
    # topology: the named pipeline topology (e.g. "chat_fast", "voice_accurate")
    topology: str | None = None
    # configuration: static wiring/configuration for this topology (optional snapshot)
    configuration: dict[str, Any] = field(default_factory=dict)
    # execution_mode: high-level execution mode label (e.g. "practice", "roleplay", "doc_edit")
    execution_mode: str | None = None
    service: str = "pipeline"
    event_sink: EventSink = field(default_factory=get_event_sink)
    data: dict[str, Any] = field(default_factory=dict)
    # Generic database session - type depends on implementation
    db: Any = None
    # Cancellation support
    canceled: bool = False
    # Artifacts produced by stages
    artifacts: list[Artifact] = field(default_factory=list)
    # Per-stage metadata for observability
    _stage_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Subpipeline support - parent/child correlation
    parent_run_id: UUID | None = None
    parent_stage_id: str | None = None
    correlation_id: UUID | None = None
    # Read-only parent data for child contexts
    _parent_data: FrozenDict[str, Any] | None = None

    def record_stage_event(
        self,
        *,
        stage: str,
        status: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Emit a timestamped stage event for observability."""
        timestamp = datetime.now(UTC).isoformat()
        event_payload = {
            "stage": stage,
            "status": status,
            "timestamp": timestamp,
            "topology": self.topology,
            "execution_mode": self.execution_mode,
        }
        if payload:
            event_payload.update(payload)

        data = {
            "request_id": str(self.request_id) if self.request_id else None,
            "session_id": str(self.session_id) if self.session_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "org_id": str(self.org_id) if self.org_id else None,
            "service": self.service,
            **event_payload,
        }
        if self.pipeline_run_id:
            data["pipeline_run_id"] = str(self.pipeline_run_id)

        self.event_sink.try_emit(type=f"stage.{stage}.{status}", data=data)

    def set_stage_metadata(self, stage: str, metadata: dict[str, Any]) -> None:
        """Set metadata for a stage."""
        self._stage_metadata[stage] = metadata

    def get_stage_metadata(self, stage: str) -> dict[str, Any] | None:
        """Get metadata for a stage."""
        return self._stage_metadata.get(stage)

    def to_dict(self) -> dict[str, Any]:
        """Convert context to a dict for tool execution."""
        result = {
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "request_id": str(self.request_id) if self.request_id else None,
            "session_id": str(self.session_id) if self.session_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "org_id": str(self.org_id) if self.org_id else None,
            "interaction_id": str(self.interaction_id) if self.interaction_id else None,
            "topology": self.topology,
            "execution_mode": self.execution_mode,
            "service": self.service,
            "data": self.data,
            "canceled": self.canceled,
            "artifacts_count": len(self.artifacts),
        }
        # Add parent correlation for child contexts
        if self.parent_run_id:
            result["parent_run_id"] = str(self.parent_run_id)
        if self.parent_stage_id:
            result["parent_stage_id"] = self.parent_stage_id
        if self.correlation_id:
            result["correlation_id"] = str(self.correlation_id)
        return result

    @classmethod
    def now(cls) -> datetime:
        """Return current UTC timestamp for consistent stage timing."""
        return datetime.now(UTC)

    @property
    def is_child_run(self) -> bool:
        """Check if this context is for a child/subpipeline run."""
        return self.parent_run_id is not None

    def get_parent_data(self, key: str, default: Any = None) -> Any:
        """Get data from parent context (for child runs).

        Args:
            key: The key to retrieve from parent data
            default: Default value if key not found

        Returns:
            The value from parent data or default
        """
        if self._parent_data is None:
            return default
        return self._parent_data.get(key, default)

    def fork(
        self,
        child_run_id: UUID,
        parent_stage_id: str,
        correlation_id: UUID,
        *,
        topology: str | None = None,
        execution_mode: str | None = None,
    ) -> PipelineContext:
        """Create a child context for a subpipeline run.

        The child context:
        - Has its own pipeline_run_id
        - References parent via parent_run_id and parent_stage_id
        - Gets a read-only snapshot of parent data
        - Inherits auth context (user_id, org_id, session_id)
        - Has its own fresh data dict and artifacts list

        Args:
            child_run_id: New pipeline run ID for the child
            parent_stage_id: The stage that is spawning this child
            correlation_id: Action ID that triggered the spawn
            topology: Optional different topology for child
            execution_mode: Optional different execution mode

        Returns:
            New PipelineContext for the child run
        """
        from stageflow.utils.frozen import FrozenDict

        return PipelineContext(
            pipeline_run_id=child_run_id,
            request_id=self.request_id,
            session_id=self.session_id,
            user_id=self.user_id,
            org_id=self.org_id,
            interaction_id=self.interaction_id,
            topology=topology or self.topology,
            configuration=self.configuration.copy(),
            execution_mode=execution_mode or self.execution_mode,
            service=self.service,
            event_sink=self.event_sink,
            data={},  # Fresh data dict for child
            db=self.db,
            canceled=False,
            artifacts=[],  # Fresh artifacts list
            _stage_metadata={},
            parent_run_id=self.pipeline_run_id,
            parent_stage_id=parent_stage_id,
            correlation_id=correlation_id,
            _parent_data=FrozenDict(self.data),
        )

    def mark_canceled(self) -> None:
        """Mark this context as canceled."""
        self.canceled = True

    @property
    def is_canceled(self) -> bool:
        """Check if this context has been canceled."""
        return self.canceled

    # === ExecutionContext protocol implementation ===

    def try_emit_event(self, type: str, data: dict[str, Any]) -> None:
        """Emit an event without blocking (fire-and-forget).

        Implements ExecutionContext protocol for compatibility with
        tools and other components.

        Args:
            type: Event type string (e.g., "tool.completed")
            data: Event payload data
        """
        # Add correlation IDs to event data
        enriched_data = {
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "request_id": str(self.request_id) if self.request_id else None,
            "execution_mode": self.execution_mode,
            "topology": self.topology,
            "service": self.service,
            **data,
        }
        self.event_sink.try_emit(type=type, data=enriched_data)

    def derive_for_stage(
        self,
        stage_name: str,
        snapshot: ContextSnapshot,
        output_bag: OutputBag,
        *,
        declared_deps: frozenset[str] | set[str] | list[str] | None = None,
        ports: CorePorts | LLMPorts | AudioPorts | None = None,
        strict: bool = True,
    ) -> StageContext:
        """Derive a StageContext for a specific stage from this PipelineContext.

        This method creates an immutable StageContext for stage execution,
        bridging between the mutable PipelineContext (used during pipeline
        orchestration) and the immutable StageContext (used during stage
        execution).

        Args:
            stage_name: Name of the stage being executed.
            snapshot: The immutable ContextSnapshot with run identity and enrichments.
            output_bag: The OutputBag containing prior stage outputs.
            declared_deps: Set of declared dependency stage names for validation.
            ports: Injected capabilities (db, callbacks, services) for the stage.
            strict: If True, raises error for undeclared dependency access.

        Returns:
            StageContext ready for stage execution.
        """
        from stageflow.core import StageContext
        from stageflow.core.timer import PipelineTimer
        from stageflow.stages.inputs import StageInputs

        # Convert deps to frozenset if provided
        deps: frozenset[str]
        if declared_deps is None:
            deps = frozenset()
        elif isinstance(declared_deps, frozenset):
            deps = declared_deps
        else:
            deps = frozenset(declared_deps)

        # Get prior outputs from the output bag
        prior_outputs = output_bag.outputs()

        # Create StageInputs with validated dependency access
        inputs = StageInputs(
            snapshot=snapshot,
            prior_outputs=prior_outputs,
            ports=ports,
            declared_deps=deps,
            stage_name=stage_name,
            strict=strict,
        )

        # Create the immutable StageContext
        return StageContext(
            snapshot=snapshot,
            inputs=inputs,
            stage_name=stage_name,
            timer=PipelineTimer(),
            event_sink=self.event_sink,
        )


__all__ = [
    "StageContext",
    "PipelineContext",
    "extract_service",
]
