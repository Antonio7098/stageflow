"""Authentication and authorization exceptions.

This module provides exception classes for authentication failures,
token validation errors, and cross-tenant access violations.
"""

from __future__ import annotations


class AuthenticationError(Exception):
    """Base exception for authentication failures.

    All authentication-related errors inherit from this class,
    enabling catch-all handling for auth failures.
    """

    def __init__(self, message: str, code: str = "auth_error") -> None:
        super().__init__(message)
        self.code = code


class TokenExpiredError(AuthenticationError):
    """Raised when a JWT token has expired.

    Attributes:
        expired_at: ISO timestamp when the token expired
    """

    def __init__(self, message: str = "Token has expired", expired_at: str | None = None) -> None:
        super().__init__(message, code="token_expired")
        self.expired_at = expired_at


class InvalidTokenError(AuthenticationError):
    """Raised when a JWT token is invalid or malformed.

    Attributes:
        reason: Specific reason for invalidity (e.g., "invalid_signature", "malformed")
    """

    def __init__(self, message: str = "Invalid token", reason: str | None = None) -> None:
        super().__init__(message, code="invalid_token")
        self.reason = reason


class MissingClaimsError(AuthenticationError):
    """Raised when required JWT claims are missing.

    Attributes:
        missing_claims: List of claim names that are missing
    """

    def __init__(
        self,
        message: str = "Required claims are missing",
        missing_claims: list[str] | None = None,
    ) -> None:
        super().__init__(message, code="missing_claims")
        self.missing_claims = missing_claims or []


class CrossTenantAccessError(AuthenticationError):
    """Raised when a user attempts to access another tenant's resources.

    Attributes:
        user_org_id: The user's organization ID
        resource_org_id: The resource's organization ID
    """

    def __init__(
        self,
        message: str = "Cross-tenant access denied",
        user_org_id: str | None = None,
        resource_org_id: str | None = None,
    ) -> None:
        super().__init__(message, code="cross_tenant_access")
        self.user_org_id = user_org_id
        self.resource_org_id = resource_org_id


__all__ = [
    "AuthenticationError",
    "CrossTenantAccessError",
    "InvalidTokenError",
    "MissingClaimsError",
    "TokenExpiredError",
]
