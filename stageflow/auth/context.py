"""Authentication and organization context types.

This module provides immutable dataclasses for representing
authenticated user context and organization context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Authenticated user context from JWT validation.

    Immutable dataclass containing user identity and authorization
    information extracted from a validated JWT token.

    Attributes:
        user_id: Unique user identifier
        email: User's email address (optional)
        org_id: Organization/tenant identifier (optional for personal accounts)
        roles: Tuple of role names assigned to the user
        session_id: Current session identifier
    """

    user_id: UUID
    session_id: UUID
    email: str | None = None
    org_id: UUID | None = None
    roles: tuple[str, ...] = field(default_factory=tuple)

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role.

        Args:
            role: Role name to check

        Returns:
            True if user has the role
        """
        return role in self.roles

    def is_admin(self) -> bool:
        """Check if user has admin privileges.

        Returns:
            True if user has 'admin' or 'org_admin' role
        """
        return self.has_role("admin") or self.has_role("org_admin")

    @property
    def is_authenticated(self) -> bool:
        """Check if this represents an authenticated user.

        Returns:
            Always True for a valid AuthContext
        """
        return True

    def __repr__(self) -> str:
        """Return string representation hiding sensitive email."""
        email_display = f"{self.email[:3]}***" if self.email else None
        return (
            f"AuthContext(user_id={self.user_id!r}, "
            f"email={email_display!r}, "
            f"org_id={self.org_id!r}, "
            f"roles={self.roles!r})"
        )


PlanTier = Literal["starter", "pro", "enterprise"]


@dataclass(frozen=True, slots=True)
class OrgContext:
    """Organization context with plan and feature information.

    Immutable dataclass containing organization metadata,
    subscription tier, and enabled features.

    Attributes:
        org_id: Organization identifier
        tenant_id: Tenant identifier (may differ from org_id in multi-tenant setups)
        plan_tier: Subscription tier level
        features: Tuple of enabled feature flags
    """

    org_id: UUID
    tenant_id: UUID | None = None
    plan_tier: PlanTier = "starter"
    features: tuple[str, ...] = field(default_factory=tuple)

    def has_feature(self, feature: str) -> bool:
        """Check if organization has a specific feature enabled.

        Args:
            feature: Feature name to check

        Returns:
            True if feature is enabled
        """
        return feature in self.features

    def __repr__(self) -> str:
        return (
            f"OrgContext(org_id={self.org_id!r}, "
            f"plan_tier={self.plan_tier!r}, "
            f"features={self.features!r})"
        )


__all__ = [
    "AuthContext",
    "OrgContext",
    "PlanTier",
]
