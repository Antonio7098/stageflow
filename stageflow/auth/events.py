"""Authentication audit event types.

This module defines structured event types for authentication
and authorization audit logging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthLoginEvent:
    """Event emitted on successful authentication.

    Attributes:
        user_id: Authenticated user ID
        org_id: Organization ID (if applicable)
        session_id: New session ID
        timestamp: When authentication occurred
        request_id: Request correlation ID
        pipeline_run_id: Pipeline run correlation ID
    """

    user_id: UUID
    session_id: UUID
    org_id: UUID | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    request_id: UUID | None = None
    pipeline_run_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for event emission."""
        return {
            "type": "auth.login",
            "user_id": str(self.user_id),
            "org_id": str(self.org_id) if self.org_id else None,
            "session_id": str(self.session_id),
            "timestamp": self.timestamp,
            "request_id": str(self.request_id) if self.request_id else None,
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
        }


@dataclass(frozen=True, slots=True)
class AuthFailureEvent:
    """Event emitted on authentication failure.

    Attributes:
        reason: Failure reason code (e.g., "token_expired", "invalid_signature")
        ip_address: Client IP address
        user_agent: Client user agent string
        timestamp: When failure occurred
        request_id: Request correlation ID
        user_id: User ID if known (e.g., from expired token)
    """

    reason: str
    ip_address: str | None = None
    user_agent: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    request_id: UUID | None = None
    user_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for event emission."""
        return {
            "type": "auth.failure",
            "reason": self.reason,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "timestamp": self.timestamp,
            "request_id": str(self.request_id) if self.request_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
        }


@dataclass(frozen=True, slots=True)
class TenantAccessDeniedEvent:
    """Event emitted on cross-tenant access attempt.

    Attributes:
        user_org_id: User's organization ID
        resource_org_id: Resource's organization ID
        user_id: User who attempted access
        timestamp: When violation occurred
        request_id: Request correlation ID
        pipeline_run_id: Pipeline run correlation ID
    """

    user_org_id: UUID
    resource_org_id: UUID
    user_id: UUID | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    request_id: UUID | None = None
    pipeline_run_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for event emission."""
        return {
            "type": "tenant.access_denied",
            "user_org_id": str(self.user_org_id),
            "resource_org_id": str(self.resource_org_id),
            "user_id": str(self.user_id) if self.user_id else None,
            "timestamp": self.timestamp,
            "request_id": str(self.request_id) if self.request_id else None,
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
        }


__all__ = [
    "AuthFailureEvent",
    "AuthLoginEvent",
    "TenantAccessDeniedEvent",
]
