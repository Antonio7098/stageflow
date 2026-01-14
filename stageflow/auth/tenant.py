"""Multi-tenant isolation utilities for stageflow.

This module provides utilities for enforcing tenant isolation in
multi-tenant deployments. While the framework provides logical isolation
via org_id in ContextSnapshot, this module adds validation helpers
and enforcement mechanisms.

Features:
- Tenant context validation
- Cross-tenant access detection
- Tenant-aware logging helpers
- Isolation boundary enforcement

Note: This module provides application-level isolation. For production
deployments, combine with infrastructure-level isolation (RLS, network
segmentation, etc.).
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, TypeVar
from uuid import UUID

logger = logging.getLogger("stageflow.auth.tenant")

T = TypeVar("T")

# Context variable for current tenant
_current_tenant: ContextVar[UUID | None] = ContextVar("current_tenant", default=None)


class TenantIsolationError(Exception):
    """Raised when tenant isolation is violated."""

    def __init__(
        self,
        message: str,
        *,
        expected_org_id: UUID | None = None,
        actual_org_id: UUID | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(message)
        self.expected_org_id = expected_org_id
        self.actual_org_id = actual_org_id
        self.operation = operation


@dataclass
class TenantContext:
    """Context for tenant-scoped operations.

    Provides utilities for validating and enforcing tenant boundaries.

    Example:
        tenant_ctx = TenantContext(org_id=uuid4())

        # Validate access
        tenant_ctx.validate_access(resource_org_id)

        # Get tenant-scoped logger
        log = tenant_ctx.get_logger("my_module")
        log.info("Processing request")  # Automatically includes org_id
    """

    org_id: UUID
    user_id: UUID | None = None
    session_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate_access(self, resource_org_id: UUID | None, *, operation: str = "access") -> None:
        """Validate that access to a resource is allowed.

        Args:
            resource_org_id: The org_id of the resource being accessed.
            operation: Description of the operation for error messages.

        Raises:
            TenantIsolationError: If the resource belongs to a different tenant.
        """
        if resource_org_id is None:
            # Resource has no tenant - allow access (shared resource)
            return

        if resource_org_id != self.org_id:
            logger.warning(
                f"Cross-tenant access attempt blocked: {operation}",
                extra={
                    "event": "tenant_isolation_violation",
                    "expected_org_id": str(self.org_id),
                    "actual_org_id": str(resource_org_id),
                    "operation": operation,
                },
            )
            raise TenantIsolationError(
                f"Cross-tenant access denied: {operation}",
                expected_org_id=self.org_id,
                actual_org_id=resource_org_id,
                operation=operation,
            )

    def get_logger(self, name: str) -> TenantAwareLogger:
        """Get a logger that automatically includes tenant context.

        Args:
            name: Logger name.

        Returns:
            TenantAwareLogger instance.
        """
        return TenantAwareLogger(name, tenant_context=self)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "org_id": str(self.org_id),
            "user_id": str(self.user_id) if self.user_id else None,
            "session_id": str(self.session_id) if self.session_id else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_snapshot(cls, snapshot) -> TenantContext | None:
        """Create TenantContext from a ContextSnapshot.

        Args:
            snapshot: ContextSnapshot instance.

        Returns:
            TenantContext if org_id is present, None otherwise.
        """
        if snapshot.org_id is None:
            return None

        return cls(
            org_id=snapshot.org_id,
            user_id=snapshot.user_id,
            session_id=snapshot.session_id,
        )


class TenantAwareLogger:
    """Logger wrapper that automatically includes tenant context.

    All log messages include org_id and other tenant metadata
    for easier filtering and audit trails.
    """

    def __init__(self, name: str, *, tenant_context: TenantContext) -> None:
        self._logger = logging.getLogger(name)
        self._tenant_context = tenant_context

    def _add_tenant_context(self, extra: dict[str, Any] | None) -> dict[str, Any]:
        """Add tenant context to extra dict."""
        result = {
            "org_id": str(self._tenant_context.org_id),
            "user_id": str(self._tenant_context.user_id) if self._tenant_context.user_id else None,
            "session_id": str(self._tenant_context.session_id) if self._tenant_context.session_id else None,
        }
        if extra:
            result.update(extra)
        return result

    def debug(self, msg: str, *args, extra: dict[str, Any] | None = None, **kwargs) -> None:
        self._logger.debug(msg, *args, extra=self._add_tenant_context(extra), **kwargs)

    def info(self, msg: str, *args, extra: dict[str, Any] | None = None, **kwargs) -> None:
        self._logger.info(msg, *args, extra=self._add_tenant_context(extra), **kwargs)

    def warning(self, msg: str, *args, extra: dict[str, Any] | None = None, **kwargs) -> None:
        self._logger.warning(msg, *args, extra=self._add_tenant_context(extra), **kwargs)

    def error(self, msg: str, *args, extra: dict[str, Any] | None = None, **kwargs) -> None:
        self._logger.error(msg, *args, extra=self._add_tenant_context(extra), **kwargs)

    def exception(self, msg: str, *args, extra: dict[str, Any] | None = None, **kwargs) -> None:
        self._logger.exception(msg, *args, extra=self._add_tenant_context(extra), **kwargs)


@dataclass
class TenantIsolationValidator:
    """Validator for ensuring tenant isolation across pipeline execution.

    Tracks all org_ids encountered during execution and validates
    that no cross-tenant data access occurs.

    Example:
        validator = TenantIsolationValidator(expected_org_id=org_id)

        # During execution, record all accessed org_ids
        validator.record_access(resource_org_id, resource_type="document")

        # At the end, verify isolation
        violations = validator.get_violations()
        if violations:
            raise TenantIsolationError(f"Violations: {violations}")
    """

    expected_org_id: UUID
    strict: bool = True
    _accessed_org_ids: dict[UUID, list[str]] = field(default_factory=dict)
    _violations: list[dict[str, Any]] = field(default_factory=list)

    def record_access(
        self,
        org_id: UUID | None,
        *,
        resource_type: str = "unknown",
        resource_id: str | None = None,
    ) -> bool:
        """Record an access to a resource and check for violations.

        Args:
            org_id: The org_id of the accessed resource.
            resource_type: Type of resource being accessed.
            resource_id: Optional identifier for the resource.

        Returns:
            True if access is allowed, False if it's a violation.
        """
        if org_id is None:
            # Shared resource, always allowed
            return True

        # Track the access
        if org_id not in self._accessed_org_ids:
            self._accessed_org_ids[org_id] = []
        self._accessed_org_ids[org_id].append(f"{resource_type}:{resource_id or 'unknown'}")

        # Check for violation
        if org_id != self.expected_org_id:
            violation = {
                "expected_org_id": str(self.expected_org_id),
                "actual_org_id": str(org_id),
                "resource_type": resource_type,
                "resource_id": resource_id,
            }
            self._violations.append(violation)
            logger.warning(
                f"Tenant isolation violation: {resource_type}",
                extra={"event": "tenant_violation", **violation},
            )
            if self.strict:
                raise TenantIsolationError(
                    f"Cross-tenant access to {resource_type}",
                    expected_org_id=self.expected_org_id,
                    actual_org_id=org_id,
                    operation=f"access_{resource_type}",
                )
            return False

        return True

    def get_violations(self) -> list[dict[str, Any]]:
        """Get all recorded violations."""
        return self._violations.copy()

    def get_accessed_tenants(self) -> list[UUID]:
        """Get all org_ids that were accessed."""
        return list(self._accessed_org_ids.keys())

    def is_isolated(self) -> bool:
        """Check if execution was properly isolated to expected tenant."""
        return len(self._violations) == 0


def set_current_tenant(org_id: UUID | None) -> None:
    """Set the current tenant in context.

    Args:
        org_id: The org_id to set as current tenant.
    """
    _current_tenant.set(org_id)


def get_current_tenant() -> UUID | None:
    """Get the current tenant from context.

    Returns:
        The current org_id or None if not set.
    """
    return _current_tenant.get()


def clear_current_tenant() -> None:
    """Clear the current tenant from context."""
    _current_tenant.set(None)


def require_tenant() -> UUID:
    """Get the current tenant, raising if not set.

    Returns:
        The current org_id.

    Raises:
        TenantIsolationError: If no tenant is set.
    """
    tenant = get_current_tenant()
    if tenant is None:
        raise TenantIsolationError("No tenant context set")
    return tenant


__all__ = [
    "TenantContext",
    "TenantAwareLogger",
    "TenantIsolationError",
    "TenantIsolationValidator",
    "set_current_tenant",
    "get_current_tenant",
    "clear_current_tenant",
    "require_tenant",
]
