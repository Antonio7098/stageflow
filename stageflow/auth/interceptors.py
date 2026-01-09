"""Authentication and tenancy enforcement interceptors.

This module provides interceptors for JWT validation and
org isolation enforcement in the pipeline execution chain.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from stageflow.auth.context import AuthContext
from stageflow.auth.errors import (
    AuthenticationError,
    InvalidTokenError,
    MissingClaimsError,
    TokenExpiredError,
)
from stageflow.auth.events import AuthFailureEvent, AuthLoginEvent, TenantAccessDeniedEvent
from stageflow.pipeline.interceptors import BaseInterceptor, InterceptorResult
from stageflow.stages.result import StageResult

if TYPE_CHECKING:
    from stageflow.stages.context import PipelineContext

logger = logging.getLogger("auth_interceptor")


class JwtValidator(Protocol):
    """Protocol for JWT validation implementations.

    Implementations should validate the token signature, expiration,
    and extract claims. Different providers (Clerk, WorkOS, etc.)
    can implement this protocol.
    """

    async def validate(self, token: str) -> dict[str, Any]:
        """Validate a JWT token and return claims.

        Args:
            token: The JWT token string

        Returns:
            Dictionary of validated claims

        Raises:
            TokenExpiredError: If token has expired
            InvalidTokenError: If token is malformed or signature invalid
            MissingClaimsError: If required claims are missing
        """
        ...


class MockJwtValidator:
    """Mock JWT validator for testing.

    Validates tokens in format "valid_<user_id>_<org_id>_<roles>"
    or rejects tokens starting with "invalid_" or "expired_".

    For testing, user_id and org_id should be valid UUID strings.
    """

    async def validate(self, token: str) -> dict[str, Any]:
        """Validate a mock JWT token."""
        if token.startswith("expired_"):
            raise TokenExpiredError("Token has expired")

        if token.startswith("invalid_"):
            raise InvalidTokenError("Invalid token signature")

        if token.startswith("missing_"):
            raise MissingClaimsError("Missing required claims", missing_claims=["user_id"])

        if token.startswith("valid_"):
            parts = token.split("_")
            # Use valid UUIDs - parts[1] and parts[2] should be UUID strings or we use defaults
            user_id = parts[1] if len(parts) > 1 and len(parts[1]) == 36 else "00000000-0000-0000-0000-000000000001"
            org_id = parts[2] if len(parts) > 2 and len(parts[2]) == 36 else None
            roles = tuple(parts[3].split(",")) if len(parts) > 3 and parts[3] else ()

            return {
                "user_id": user_id,
                "org_id": org_id,
                "email": "user@example.com",
                "session_id": "00000000-0000-0000-0000-000000000099",
                "roles": roles,
            }

        # Default: treat as valid token with minimal claims
        return {
            "user_id": "00000000-0000-0000-0000-000000000001",
            "session_id": "00000000-0000-0000-0000-000000000099",
            "roles": (),
        }


class AuthInterceptor(BaseInterceptor):
    """Validates JWT and populates AuthContext.

    This interceptor runs first (priority=1) to validate authentication
    before any other processing occurs. On success, it populates the
    AuthContext in the pipeline context data.

    Attributes:
        name: Interceptor name for logging
        priority: Execution priority (1 = runs first)
    """

    name: str = "auth"
    priority: int = 1  # Runs first (before circuit breaker)

    def __init__(self, jwt_validator: JwtValidator | None = None) -> None:
        """Initialize with optional JWT validator.

        Args:
            jwt_validator: JWT validation implementation (defaults to MockJwtValidator)
        """
        self._jwt_validator = jwt_validator or MockJwtValidator()

    async def before(self, _stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        """Validate JWT token before stage execution.

        Extracts token from ctx.data["_auth_token"] or ctx.data.get("auth_token").
        On success, stores AuthContext in ctx.data["_auth_context"] and sets
        ctx.user_id and ctx.org_id.

        Args:
            stage_name: Name of stage about to execute
            ctx: Pipeline execution context

        Returns:
            None to continue, or InterceptorResult to short-circuit on auth failure
        """
        # Get token from context
        token = ctx.data.get("_auth_token") or ctx.data.get("auth_token")

        if not token:
            await self._emit_auth_failure(ctx, "missing_token")
            return InterceptorResult(
                stage_ran=False,
                error="Missing authentication token",
            )

        try:
            auth_context = await self._validate_token(token)
            ctx.data["_auth_context"] = auth_context

            # Set context user/org IDs
            # Note: PipelineContext is a dataclass with slots, so we store in data dict
            ctx.data["_user_id"] = auth_context.user_id
            ctx.data["_org_id"] = auth_context.org_id

            # Emit login event
            await self._emit_auth_login(ctx, auth_context)

            return None

        except AuthenticationError as e:
            await self._emit_auth_failure(ctx, e.code, str(e))
            return InterceptorResult(
                stage_ran=False,
                error=str(e),
            )

    async def after(self, _stage_name: str, _result: StageResult, _ctx: PipelineContext) -> None:
        """No-op after hook."""
        pass

    async def _validate_token(self, token: str) -> AuthContext:
        """Validate JWT and create AuthContext.

        Args:
            token: JWT token string

        Returns:
            Validated AuthContext

        Raises:
            AuthenticationError: On validation failure
        """
        claims = await self._jwt_validator.validate(token)

        # Extract required claims
        user_id_str = claims.get("user_id")
        session_id_str = claims.get("session_id")

        if not user_id_str:
            raise MissingClaimsError("Missing user_id claim", missing_claims=["user_id"])
        if not session_id_str:
            raise MissingClaimsError("Missing session_id claim", missing_claims=["session_id"])

        # Parse UUIDs
        try:
            user_id = UUID(user_id_str)
            session_id = UUID(session_id_str)
            org_id = UUID(claims["org_id"]) if claims.get("org_id") else None
        except ValueError as e:
            raise InvalidTokenError(f"Invalid UUID in claims: {e}") from e

        # Extract optional claims
        email = claims.get("email")
        roles = tuple(claims.get("roles", []))

        return AuthContext(
            user_id=user_id,
            session_id=session_id,
            email=email,
            org_id=org_id,
            roles=roles,
        )

    async def _emit_auth_login(self, ctx: PipelineContext, auth_context: AuthContext) -> None:
        """Emit auth.login event."""
        event = AuthLoginEvent(
            user_id=auth_context.user_id,
            session_id=auth_context.session_id,
            org_id=auth_context.org_id,
            request_id=ctx.request_id,
            pipeline_run_id=ctx.pipeline_run_id,
        )
        ctx.event_sink.try_emit(type="auth.login", data=event.to_dict())
        logger.info(
            "Authentication successful",
            extra={
                "user_id": str(auth_context.user_id),
                "org_id": str(auth_context.org_id) if auth_context.org_id else None,
            },
        )

    async def _emit_auth_failure(
        self, ctx: PipelineContext, reason: str, error_message: str | None = None
    ) -> None:
        """Emit auth.failure event."""
        event = AuthFailureEvent(
            reason=reason,
            request_id=ctx.request_id,
            ip_address=ctx.data.get("_client_ip"),
            user_agent=ctx.data.get("_user_agent"),
        )
        ctx.event_sink.try_emit(type="auth.failure", data=event.to_dict())
        logger.warning(
            f"Authentication failed: {reason}",
            extra={"reason": reason, "error_detail": error_message},
        )


class OrgEnforcementInterceptor(BaseInterceptor):
    """Enforces tenant isolation on all resource access.

    This interceptor runs after auth (priority=2) to verify that
    the authenticated user is accessing resources within their
    own organization.

    Attributes:
        name: Interceptor name for logging
        priority: Execution priority (2 = after auth)
    """

    name: str = "org_enforcement"
    priority: int = 2  # Runs after auth

    async def before(self, _stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        """Check org isolation before stage execution.

        Verifies that ctx.data["_resource_org_id"] matches the
        authenticated user's org_id if both are present.

        Args:
            stage_name: Name of stage about to execute
            ctx: Pipeline execution context

        Returns:
            None to continue, or InterceptorResult to deny cross-tenant access
        """
        auth_context: AuthContext | None = ctx.data.get("_auth_context")

        if not auth_context:
            # No auth context - auth interceptor should have run first
            return InterceptorResult(
                stage_ran=False,
                error="AuthContext not available - ensure AuthInterceptor runs first",
            )

        # Check for resource org_id
        resource_org_id = ctx.data.get("_resource_org_id")

        if resource_org_id is not None:
            # Parse if string
            if isinstance(resource_org_id, str):
                try:
                    resource_org_id = UUID(resource_org_id)
                except ValueError:
                    return InterceptorResult(
                        stage_ran=False,
                        error=f"Invalid resource_org_id format: {resource_org_id}",
                    )

            # Check for cross-tenant access
            if auth_context.org_id and resource_org_id != auth_context.org_id:
                await self._emit_tenant_violation(ctx, auth_context, resource_org_id)
                return InterceptorResult(
                    stage_ran=False,
                    error="Cross-tenant access denied",
                )

        return None

    async def after(self, _stage_name: str, _result: StageResult, _ctx: PipelineContext) -> None:
        """No-op after hook."""
        pass

    async def _emit_tenant_violation(
        self, ctx: PipelineContext, auth_context: AuthContext, resource_org_id: UUID
    ) -> None:
        """Emit tenant.access_denied event."""
        event = TenantAccessDeniedEvent(
            user_org_id=auth_context.org_id,  # type: ignore - we know it's not None here
            resource_org_id=resource_org_id,
            user_id=auth_context.user_id,
            request_id=ctx.request_id,
            pipeline_run_id=ctx.pipeline_run_id,
        )
        ctx.event_sink.try_emit(type="tenant.access_denied", data=event.to_dict())
        logger.warning(
            "Cross-tenant access denied",
            extra={
                "user_org_id": str(auth_context.org_id),
                "resource_org_id": str(resource_org_id),
                "user_id": str(auth_context.user_id),
            },
        )


__all__ = [
    "AuthInterceptor",
    "JwtValidator",
    "MockJwtValidator",
    "OrgEnforcementInterceptor",
]
