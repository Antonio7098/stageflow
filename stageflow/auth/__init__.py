"""Stageflow auth module - authentication and authorization types."""

from stageflow.auth.context import AuthContext, OrgContext
from stageflow.auth.errors import (
    AuthenticationError,
    CrossTenantAccessError,
    InvalidTokenError,
    MissingClaimsError,
    TokenExpiredError,
)
from stageflow.auth.events import (
    AuthFailureEvent,
    AuthLoginEvent,
    TenantAccessDeniedEvent,
)
from stageflow.auth.interceptors import (
    AuthInterceptor,
    JwtValidator,
    MockJwtValidator,
    OrgEnforcementInterceptor,
)

__all__ = [
    "AuthContext",
    "AuthenticationError",
    "AuthFailureEvent",
    "AuthInterceptor",
    "AuthLoginEvent",
    "CrossTenantAccessError",
    "InvalidTokenError",
    "JwtValidator",
    "MissingClaimsError",
    "MockJwtValidator",
    "OrgContext",
    "OrgEnforcementInterceptor",
    "TenantAccessDeniedEvent",
    "TokenExpiredError",
]
