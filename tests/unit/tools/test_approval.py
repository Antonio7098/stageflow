"""Unit tests for approval service."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from stageflow.tools.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalService,
    ApprovalStatus,
    clear_approval_service,
    get_approval_service,
)


class TestApprovalRequest:
    """Tests for ApprovalRequest dataclass."""

    def test_create_approval_request(self) -> None:
        """Create an ApprovalRequest."""
        request = ApprovalRequest(
            id=uuid4(),
            action_id=uuid4(),
            tool_name="test_tool",
            approval_message="Approve this?",
        )
        assert request.status == ApprovalStatus.PENDING
        assert request.decided_by is None

    def test_request_to_dict(self) -> None:
        """ApprovalRequest serializes to dictionary."""
        request_id = uuid4()
        request = ApprovalRequest(
            id=request_id,
            action_id=uuid4(),
            tool_name="test_tool",
        )
        result = request.to_dict()
        assert result["id"] == str(request_id)
        assert result["status"] == "pending"


class TestApprovalDecision:
    """Tests for ApprovalDecision dataclass."""

    def test_create_approved_decision(self) -> None:
        """Create an approved decision."""
        decision = ApprovalDecision(
            request_id=uuid4(),
            granted=True,
            decided_by=uuid4(),
        )
        assert decision.granted is True

    def test_create_denied_decision(self) -> None:
        """Create a denied decision."""
        decision = ApprovalDecision(
            request_id=uuid4(),
            granted=False,
            reason="Too risky",
        )
        assert decision.granted is False
        assert decision.reason == "Too risky"


class TestApprovalService:
    """Tests for ApprovalService."""

    @pytest.fixture
    def service(self) -> ApprovalService:
        """Create a fresh ApprovalService."""
        return ApprovalService(default_timeout_seconds=1.0)

    @pytest.mark.asyncio
    async def test_request_approval_creates_request(self, service: ApprovalService) -> None:
        """request_approval() creates a pending request."""
        action_id = uuid4()
        request = await service.request_approval(
            action_id=action_id,
            tool_name="test_tool",
            approval_message="Approve?",
        )

        assert request.action_id == action_id
        assert request.tool_name == "test_tool"
        assert request.status == ApprovalStatus.PENDING

    @pytest.mark.asyncio
    async def test_record_decision_approved(self, service: ApprovalService) -> None:
        """record_decision() updates request with approval."""
        request = await service.request_approval(
            action_id=uuid4(),
            tool_name="test_tool",
        )

        user_id = uuid4()
        decision = await service.record_decision(
            request_id=request.id,
            granted=True,
            decided_by=user_id,
        )

        assert decision.granted is True
        assert decision.decided_by == user_id

        updated = await service.get_request(request.id)
        assert updated.status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_record_decision_denied(self, service: ApprovalService) -> None:
        """record_decision() updates request with denial."""
        request = await service.request_approval(
            action_id=uuid4(),
            tool_name="test_tool",
        )

        decision = await service.record_decision(
            request_id=request.id,
            granted=False,
            reason="Not allowed",
        )

        assert decision.granted is False
        assert decision.reason == "Not allowed"

        updated = await service.get_request(request.id)
        assert updated.status == ApprovalStatus.DENIED

    @pytest.mark.asyncio
    async def test_await_decision_returns_after_record(self, service: ApprovalService) -> None:
        """await_decision() returns when decision is recorded."""
        request = await service.request_approval(
            action_id=uuid4(),
            tool_name="test_tool",
        )

        async def approve_after_delay():
            await asyncio.sleep(0.1)
            await service.record_decision(request.id, granted=True)

        # Start approval in background
        asyncio.create_task(approve_after_delay())

        # Wait for decision
        decision = await service.await_decision(request.id, timeout_seconds=2.0)

        assert decision.granted is True

    @pytest.mark.asyncio
    async def test_await_decision_timeout(self, service: ApprovalService) -> None:
        """await_decision() raises TimeoutError on timeout."""
        request = await service.request_approval(
            action_id=uuid4(),
            tool_name="test_tool",
        )

        with pytest.raises(asyncio.TimeoutError):
            await service.await_decision(request.id, timeout_seconds=0.1)

        updated = await service.get_request(request.id)
        assert updated.status == ApprovalStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_cancel_request(self, service: ApprovalService) -> None:
        """cancel_request() cancels a pending request."""
        request = await service.request_approval(
            action_id=uuid4(),
            tool_name="test_tool",
        )

        cancelled = await service.cancel_request(request.id)
        assert cancelled is True

        updated = await service.get_request(request.id)
        assert updated.status == ApprovalStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_get_pending_requests(self, service: ApprovalService) -> None:
        """get_pending_requests() returns only pending requests."""
        run_id = uuid4()

        # Create some requests
        req1 = await service.request_approval(uuid4(), "tool1", pipeline_run_id=run_id)
        req2 = await service.request_approval(uuid4(), "tool2", pipeline_run_id=run_id)
        req3 = await service.request_approval(uuid4(), "tool3", pipeline_run_id=uuid4())

        # Approve one
        await service.record_decision(req1.id, granted=True)

        # Get pending for our run
        pending = await service.get_pending_requests(pipeline_run_id=run_id)

        assert len(pending) == 1
        assert pending[0].id == req2.id

    @pytest.mark.asyncio
    async def test_cleanup_removes_request(self, service: ApprovalService) -> None:
        """cleanup() removes request data."""
        request = await service.request_approval(
            action_id=uuid4(),
            tool_name="test_tool",
        )

        await service.cleanup(request.id)

        result = await service.get_request(request.id)
        assert result is None


class TestApprovalServiceGlobals:
    """Tests for global approval service functions."""

    def teardown_method(self) -> None:
        """Clear global service after each test."""
        clear_approval_service()

    def test_get_approval_service_creates_singleton(self) -> None:
        """get_approval_service() returns same instance."""
        service1 = get_approval_service()
        service2 = get_approval_service()
        assert service1 is service2

    def test_clear_approval_service(self) -> None:
        """clear_approval_service() resets the singleton."""
        service1 = get_approval_service()
        clear_approval_service()
        service2 = get_approval_service()
        assert service1 is not service2
