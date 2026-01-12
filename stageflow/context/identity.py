"""RunIdentity - Grouped run identification fields.

This module provides the RunIdentity dataclass that groups all run-related
identity fields into a single, immutable structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class RunIdentity:
    """Grouped run identification fields.

    Contains all IDs needed to identify and correlate a pipeline run
    within the system. All fields are optional to support testing
    and simple use cases.

    Attributes:
        pipeline_run_id: Unique identifier for this pipeline execution.
        request_id: HTTP/WS request that triggered the pipeline.
        session_id: User session identifier.
        user_id: User who initiated the request.
        org_id: Organization/tenant identifier.
        interaction_id: Specific interaction within a session.
        created_at: When this identity was created.

    Example:
        identity = RunIdentity(
            pipeline_run_id=uuid4(),
            user_id=uuid4(),
        )
    """

    pipeline_run_id: UUID | None = None
    request_id: UUID | None = None
    session_id: UUID | None = None
    user_id: UUID | None = None
    org_id: UUID | None = None
    interaction_id: UUID | None = None
    created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary.

        Returns:
            Dict with string representations of UUIDs.
        """
        return {
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "request_id": str(self.request_id) if self.request_id else None,
            "session_id": str(self.session_id) if self.session_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "org_id": str(self.org_id) if self.org_id else None,
            "interaction_id": str(self.interaction_id) if self.interaction_id else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunIdentity:
        """Create RunIdentity from a dictionary.

        Args:
            data: Dictionary with identity fields.

        Returns:
            RunIdentity instance.
        """
        created_at = _utc_now()
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        return cls(
            pipeline_run_id=UUID(data["pipeline_run_id"]) if data.get("pipeline_run_id") else None,
            request_id=UUID(data["request_id"]) if data.get("request_id") else None,
            session_id=UUID(data["session_id"]) if data.get("session_id") else None,
            user_id=UUID(data["user_id"]) if data.get("user_id") else None,
            org_id=UUID(data["org_id"]) if data.get("org_id") else None,
            interaction_id=UUID(data["interaction_id"]) if data.get("interaction_id") else None,
            created_at=created_at,
        )

    def with_pipeline_run_id(self, pipeline_run_id: UUID) -> RunIdentity:
        """Return a copy with a new pipeline_run_id.

        Args:
            pipeline_run_id: The new pipeline run ID.

        Returns:
            New RunIdentity with the updated field.
        """
        return RunIdentity(
            pipeline_run_id=pipeline_run_id,
            request_id=self.request_id,
            session_id=self.session_id,
            user_id=self.user_id,
            org_id=self.org_id,
            interaction_id=self.interaction_id,
            created_at=self.created_at,
        )


__all__ = ["RunIdentity"]
