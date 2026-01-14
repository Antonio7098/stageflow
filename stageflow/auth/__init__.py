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
from stageflow.auth.tenant import (
    TenantAwareLogger,
    TenantContext,
    TenantIsolationError,
    TenantIsolationValidator,
    clear_current_tenant,
    get_current_tenant,
    require_tenant,
    set_current_tenant,
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
    "TenantAwareLogger",
    "TenantContext",
    "TenantIsolationError",
    "TenantIsolationValidator",
    "TokenExpiredError",
    "clear_current_tenant",
    "get_current_tenant",
    "require_tenant",
    "set_current_tenant",
]
