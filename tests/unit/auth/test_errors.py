"""Unit tests for auth exception classes."""

import pytest

from stageflow.auth.errors import (
    AuthenticationError,
    CrossTenantAccessError,
    InvalidTokenError,
    MissingClaimsError,
    TokenExpiredError,
)


class TestAuthenticationError:
    """Tests for base AuthenticationError."""

    def test_error_with_message(self):
        """Test creating error with message."""
        error = AuthenticationError("Auth failed")
        assert str(error) == "Auth failed"
        assert error.code == "auth_error"

    def test_error_with_custom_code(self):
        """Test creating error with custom code."""
        error = AuthenticationError("Auth failed", code="custom_error")
        assert error.code == "custom_error"

    def test_error_is_exception(self):
        """Test that error can be raised and caught."""
        with pytest.raises(AuthenticationError):
            raise AuthenticationError("Test error")


class TestTokenExpiredError:
    """Tests for TokenExpiredError."""

    def test_default_message(self):
        """Test default error message."""
        error = TokenExpiredError()
        assert "expired" in str(error).lower()
        assert error.code == "token_expired"

    def test_custom_message(self):
        """Test custom error message."""
        error = TokenExpiredError("Token expired at midnight")
        assert str(error) == "Token expired at midnight"

    def test_expired_at_attribute(self):
        """Test expired_at attribute."""
        error = TokenExpiredError(expired_at="2024-01-01T00:00:00Z")
        assert error.expired_at == "2024-01-01T00:00:00Z"

    def test_inherits_from_auth_error(self):
        """Test inheritance from AuthenticationError."""
        error = TokenExpiredError()
        assert isinstance(error, AuthenticationError)


class TestInvalidTokenError:
    """Tests for InvalidTokenError."""

    def test_default_message(self):
        """Test default error message."""
        error = InvalidTokenError()
        assert "invalid" in str(error).lower()
        assert error.code == "invalid_token"

    def test_reason_attribute(self):
        """Test reason attribute."""
        error = InvalidTokenError(reason="invalid_signature")
        assert error.reason == "invalid_signature"

    def test_inherits_from_auth_error(self):
        """Test inheritance from AuthenticationError."""
        error = InvalidTokenError()
        assert isinstance(error, AuthenticationError)


class TestMissingClaimsError:
    """Tests for MissingClaimsError."""

    def test_default_message(self):
        """Test default error message."""
        error = MissingClaimsError()
        assert "missing" in str(error).lower()
        assert error.code == "missing_claims"

    def test_missing_claims_attribute(self):
        """Test missing_claims attribute."""
        error = MissingClaimsError(missing_claims=["user_id", "email"])
        assert error.missing_claims == ["user_id", "email"]

    def test_default_missing_claims_is_empty(self):
        """Test default missing_claims is empty list."""
        error = MissingClaimsError()
        assert error.missing_claims == []

    def test_inherits_from_auth_error(self):
        """Test inheritance from AuthenticationError."""
        error = MissingClaimsError()
        assert isinstance(error, AuthenticationError)


class TestCrossTenantAccessError:
    """Tests for CrossTenantAccessError."""

    def test_default_message(self):
        """Test default error message."""
        error = CrossTenantAccessError()
        assert "cross-tenant" in str(error).lower() or "denied" in str(error).lower()
        assert error.code == "cross_tenant_access"

    def test_org_id_attributes(self):
        """Test org_id attributes."""
        error = CrossTenantAccessError(
            user_org_id="org-123",
            resource_org_id="org-456",
        )
        assert error.user_org_id == "org-123"
        assert error.resource_org_id == "org-456"

    def test_inherits_from_auth_error(self):
        """Test inheritance from AuthenticationError."""
        error = CrossTenantAccessError()
        assert isinstance(error, AuthenticationError)
