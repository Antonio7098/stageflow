"""Unit tests for auth audit events."""

from uuid import uuid4

import pytest

from stageflow.auth.events import (
    AuthFailureEvent,
    AuthLoginEvent,
    TenantAccessDeniedEvent,
)


class TestAuthLoginEvent:
    """Tests for AuthLoginEvent."""

    def test_create_event(self):
        """Test creating an AuthLoginEvent."""
        user_id = uuid4()
        session_id = uuid4()
        org_id = uuid4()

        event = AuthLoginEvent(
            user_id=user_id,
            session_id=session_id,
            org_id=org_id,
        )

        assert event.user_id == user_id
        assert event.session_id == session_id
        assert event.org_id == org_id
        assert event.timestamp is not None

    def test_to_dict(self):
        """Test to_dict() returns correct structure."""
        user_id = uuid4()
        session_id = uuid4()

        event = AuthLoginEvent(user_id=user_id, session_id=session_id)
        data = event.to_dict()

        assert data["type"] == "auth.login"
        assert data["user_id"] == str(user_id)
        assert data["session_id"] == str(session_id)
        assert "timestamp" in data

    def test_event_is_immutable(self):
        """Test that event is frozen."""
        event = AuthLoginEvent(user_id=uuid4(), session_id=uuid4())

        with pytest.raises(AttributeError):
            event.user_id = uuid4()


class TestAuthFailureEvent:
    """Tests for AuthFailureEvent."""

    def test_create_event(self):
        """Test creating an AuthFailureEvent."""
        event = AuthFailureEvent(
            reason="token_expired",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        assert event.reason == "token_expired"
        assert event.ip_address == "192.168.1.1"
        assert event.user_agent == "Mozilla/5.0"

    def test_to_dict(self):
        """Test to_dict() returns correct structure."""
        event = AuthFailureEvent(reason="invalid_signature")
        data = event.to_dict()

        assert data["type"] == "auth.failure"
        assert data["reason"] == "invalid_signature"
        assert "timestamp" in data

    def test_create_minimal_event(self):
        """Test creating event with minimal fields."""
        event = AuthFailureEvent(reason="unknown")

        assert event.reason == "unknown"
        assert event.ip_address is None
        assert event.user_agent is None


class TestTenantAccessDeniedEvent:
    """Tests for TenantAccessDeniedEvent."""

    def test_create_event(self):
        """Test creating a TenantAccessDeniedEvent."""
        user_org_id = uuid4()
        resource_org_id = uuid4()
        user_id = uuid4()

        event = TenantAccessDeniedEvent(
            user_org_id=user_org_id,
            resource_org_id=resource_org_id,
            user_id=user_id,
        )

        assert event.user_org_id == user_org_id
        assert event.resource_org_id == resource_org_id
        assert event.user_id == user_id

    def test_to_dict(self):
        """Test to_dict() returns correct structure."""
        user_org_id = uuid4()
        resource_org_id = uuid4()

        event = TenantAccessDeniedEvent(
            user_org_id=user_org_id,
            resource_org_id=resource_org_id,
        )
        data = event.to_dict()

        assert data["type"] == "tenant.access_denied"
        assert data["user_org_id"] == str(user_org_id)
        assert data["resource_org_id"] == str(resource_org_id)
        assert "timestamp" in data
