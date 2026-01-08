"""Unified PipelineContext for stageflow architecture.

This module provides the canonical execution context for pipeline stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from stageflow.core.stages import StageArtifact as Artifact
from stageflow.events import EventSink, get_event_sink


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


def extract_quality_mode(topology: str | None) -> str | None:
    """Extract quality mode from topology string.

    For pipeline names like "chat_fast", returns "fast".
    For pipeline names like "voice_accurate", returns "accurate".
    For kernel names (e.g., "fast_kernel"), extracts the kernel prefix.

    Args:
        topology: The topology string (e.g., "chat_fast")

    Returns:
        Quality mode (e.g., "fast", "accurate") or None if topology is None
    """
    if topology is None:
        return None
    # Kernel names like "fast_kernel" -> "fast"
    if topology.endswith("_kernel"):
        return topology[:-7] if len(topology) > 7 else None
    # Pipeline names like "chat_fast", "voice_accurate"
    parts = topology.rsplit("_", 1)
    if len(parts) == 2 and parts[1] in ("fast", "balanced", "accurate", "practice"):
        return parts[1]
    return None


@dataclass(slots=True, kw_only=True)
class PipelineContext:
    """Execution context shared between stages."""

    pipeline_run_id: UUID | None
    request_id: UUID | None
    session_id: UUID | None
    user_id: UUID | None
    org_id: UUID | None
    interaction_id: UUID | None
    # Topology / Configuration / Behavior
    # topology: the named pipeline topology (e.g. "chat_fast", "voice_accurate")
    # This encapsulates the service ("chat", "voice") and mode (derived from kernel + channel)
    topology: str | None = None
    # configuration: static wiring/configuration for this topology (optional snapshot)
    configuration: dict[str, Any] = field(default_factory=dict)
    # behavior: high-level behavior label (e.g. "practice", "roleplay", "doc_edit")
    behavior: str | None = None
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
            "behavior": self.behavior,
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
        return {
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "request_id": str(self.request_id) if self.request_id else None,
            "session_id": str(self.session_id) if self.session_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "org_id": str(self.org_id) if self.org_id else None,
            "interaction_id": str(self.interaction_id) if self.interaction_id else None,
            "topology": self.topology,
            "behavior": self.behavior,
            "service": self.service,
            "data": self.data,
            "canceled": self.canceled,
            "artifacts_count": len(self.artifacts),
        }

    @classmethod
    def now(cls) -> datetime:
        """Return current UTC timestamp for consistent stage timing."""
        return datetime.now(UTC)


__all__ = [
    "PipelineContext",
    "extract_quality_mode",
    "extract_service",
]
