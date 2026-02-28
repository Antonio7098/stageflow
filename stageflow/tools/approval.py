"""HITL (Human-in-the-Loop) approval service for risky tool actions.

This module provides the approval request/response flow for tools that
require human approval before execution.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class ApprovalStatus(str, Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class ApprovalRequest:
    """A pending approval request.

    Attributes:
        id: Unique request identifier
        action_id: The action requiring approval
        tool_name: Name of the tool
        pipeline_run_id: Pipeline run identifier
        approval_message: Message to display to user
        status: Current status
        decided_by: User who made the decision
        decided_at: When the decision was made
        created_at: When the request was created
        payload_summary: Summary of action payload for UI
    """

    id: UUID
    action_id: UUID
    tool_name: str
    pipeline_run_id: UUID | None = None
    approval_message: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_by: UUID | None = None
    decided_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    payload_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "action_id": str(self.action_id),
            "tool_name": self.tool_name,
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "approval_message": self.approval_message,
            "status": self.status.value,
            "decided_by": str(self.decided_by) if self.decided_by else None,
            "decided_at": self.decided_at,
            "created_at": self.created_at,
            "payload_summary": self.payload_summary,
        }


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """The decision made on an approval request."""

    request_id: UUID
    granted: bool
    decided_by: UUID | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_id": str(self.request_id),
            "granted": self.granted,
            "decided_by": str(self.decided_by) if self.decided_by else None,
            "reason": self.reason,
        }


class ApprovalService:
    """Service for managing HITL approval requests.

    This is an in-memory implementation suitable for testing and
    single-instance deployments. For production, consider:
    - Database-backed implementation for persistence
    - WebSocket integration for real-time notifications
    - Redis pub/sub for multi-instance coordination

    Example:
        service = ApprovalService()
        request = await service.request_approval(
            action_id=action.id,
            tool_name="delete_file",
            approval_message="Delete important.txt?"
        )
        # In real app, send request to UI and wait for response
        decision = await service.await_decision(request.id, timeout_seconds=60)
        if decision.granted:
            # Execute tool
    """

    def __init__(self, default_timeout_seconds: float = 60.0) -> None:
        self.default_timeout_seconds = default_timeout_seconds
        self._requests: dict[UUID, ApprovalRequest] = {}
        self._decision_events: dict[UUID, asyncio.Event] = {}
        self._decisions: dict[UUID, ApprovalDecision] = {}
        self._lock = asyncio.Lock()

    async def request_approval(
        self,
        action_id: UUID,
        tool_name: str,
        pipeline_run_id: UUID | None = None,
        approval_message: str = "",
        payload_summary: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        """Create an approval request.

        Args:
            action_id: The action requiring approval
            tool_name: Name of the tool
            pipeline_run_id: Pipeline run identifier
            approval_message: Message for the approval UI
            payload_summary: Summary of action for context

        Returns:
            The created ApprovalRequest
        """
        request_id = uuid4()
        request = ApprovalRequest(
            id=request_id,
            action_id=action_id,
            tool_name=tool_name,
            pipeline_run_id=pipeline_run_id,
            approval_message=approval_message,
            payload_summary=payload_summary or {},
        )

        async with self._lock:
            self._requests[request_id] = request
            self._decision_events[request_id] = asyncio.Event()

        return request

    async def request(self, request: ApprovalRequest) -> ApprovalRequest:
        """Backward-compatible alias that accepts an ApprovalRequest object."""
        return await self.request_approval(
            action_id=request.action_id,
            tool_name=request.tool_name,
            pipeline_run_id=request.pipeline_run_id,
            approval_message=request.approval_message,
            payload_summary=request.payload_summary,
        )

    async def await_decision(
        self,
        request_id: UUID,
        timeout_seconds: float | None = None,
    ) -> ApprovalDecision:
        """Wait for an approval decision.

        Args:
            request_id: The request to wait for
            timeout_seconds: How long to wait (None uses default)

        Returns:
            The ApprovalDecision

        Raises:
            asyncio.TimeoutError: If timeout expires
            KeyError: If request not found
        """
        timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout_seconds

        async with self._lock:
            event = self._decision_events.get(request_id)
            if event is None:
                raise KeyError(f"Approval request {request_id} not found")

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except TimeoutError:
            await self._mark_expired(request_id)
            raise

        async with self._lock:
            decision = self._decisions.get(request_id)
            if decision is None:
                return ApprovalDecision(request_id=request_id, granted=False, reason="no_decision")
            return decision

    async def record_decision(
        self,
        request_id: UUID,
        granted: bool,
        decided_by: UUID | None = None,
        reason: str | None = None,
    ) -> ApprovalDecision:
        """Record an approval decision.

        Args:
            request_id: The request being decided
            granted: Whether approval was granted
            decided_by: User who made the decision
            reason: Optional reason for the decision

        Returns:
            The recorded ApprovalDecision

        Raises:
            KeyError: If request not found
        """
        decision = ApprovalDecision(
            request_id=request_id,
            granted=granted,
            decided_by=decided_by,
            reason=reason,
        )

        async with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                raise KeyError(f"Approval request {request_id} not found")

            request.status = ApprovalStatus.APPROVED if granted else ApprovalStatus.DENIED
            request.decided_by = decided_by
            request.decided_at = datetime.now(UTC).isoformat()

            self._decisions[request_id] = decision

            event = self._decision_events.get(request_id)
            if event:
                event.set()

        return decision

    async def _mark_expired(self, request_id: UUID) -> None:
        """Mark a request as expired."""
        async with self._lock:
            request = self._requests.get(request_id)
            if request and request.status == ApprovalStatus.PENDING:
                request.status = ApprovalStatus.EXPIRED

    async def cancel_request(self, request_id: UUID) -> bool:
        """Cancel a pending approval request.

        Args:
            request_id: The request to cancel

        Returns:
            True if cancelled, False if not found or already decided
        """
        async with self._lock:
            request = self._requests.get(request_id)
            if request is None or request.status != ApprovalStatus.PENDING:
                return False

            request.status = ApprovalStatus.CANCELLED
            self._decisions[request_id] = ApprovalDecision(
                request_id=request_id,
                granted=False,
                reason="cancelled",
            )

            event = self._decision_events.get(request_id)
            if event:
                event.set()

            return True

    async def get_request(self, request_id: UUID) -> ApprovalRequest | None:
        """Get an approval request by ID."""
        async with self._lock:
            return self._requests.get(request_id)

    async def get_status(self, request_or_action_id: UUID) -> ApprovalStatus | None:
        """Backward-compatible status lookup by request_id or action_id."""
        async with self._lock:
            request = self._requests.get(request_or_action_id)
            if request is not None:
                return request.status

            # Fall back to action_id lookup.
            for candidate in reversed(list(self._requests.values())):
                if candidate.action_id == request_or_action_id:
                    return candidate.status
        return None

    async def get_pending_requests(
        self,
        pipeline_run_id: UUID | None = None,
    ) -> list[ApprovalRequest]:
        """Get all pending approval requests.

        Args:
            pipeline_run_id: Optional filter by pipeline run

        Returns:
            List of pending requests
        """
        async with self._lock:
            requests = [
                r for r in self._requests.values()
                if r.status == ApprovalStatus.PENDING
            ]
            if pipeline_run_id:
                requests = [r for r in requests if r.pipeline_run_id == pipeline_run_id]
            return requests

    async def cleanup(self, request_id: UUID) -> None:
        """Clean up a completed request."""
        async with self._lock:
            self._requests.pop(request_id, None)
            self._decision_events.pop(request_id, None)
            self._decisions.pop(request_id, None)


# Global approval service instance
_approval_service: ApprovalService | None = None


def get_approval_service() -> ApprovalService:
    """Get the global approval service instance."""
    global _approval_service
    if _approval_service is None:
        _approval_service = ApprovalService()
    return _approval_service


def set_approval_service(service: ApprovalService) -> None:
    """Set the global approval service instance."""
    global _approval_service
    _approval_service = service


def clear_approval_service() -> None:
    """Clear the global approval service instance."""
    global _approval_service
    _approval_service = None


__all__ = [
    "ApprovalStatus",
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalService",
    "get_approval_service",
    "set_approval_service",
    "clear_approval_service",
]
