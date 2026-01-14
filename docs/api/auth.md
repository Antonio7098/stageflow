# Auth API Reference

This document provides the API reference for authentication and authorization types.

## AuthContext

```python
from stageflow.auth import AuthContext
from uuid import uuid4
```

Authenticated user context from JWT validation.

### Constructor

```python
AuthContext(
    user_id: UUID,
    session_id: UUID,
    email: str | None = None,
    org_id: UUID | None = None,
    roles: tuple[str, ...] = (),
)
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `user_id` | `UUID` | User identifier |
| `session_id` | `UUID` | Session identifier |
| `email` | `str \| None` | User email |
| `org_id` | `UUID \| None` | Organization identifier |
| `roles` | `tuple[str, ...]` | Assigned roles |

### Methods

#### `has_role(role: str) -> bool`

Check if user has a specific role.

#### `is_admin() -> bool`

Check if user has 'admin' or 'org_admin' role.

### Properties

#### `is_authenticated -> bool`

Always returns `True` for valid AuthContext.

### Best Practices

#### `is_authenticated -> bool`

Always returns `True` for valid AuthContext.

---

## OrgContext

```python
from stageflow.auth import OrgContext
```

Organization context with plan and feature information.

### Constructor

```python
OrgContext(
    org_id: UUID,
    tenant_id: UUID | None = None,
    plan_tier: PlanTier = "starter",
    features: tuple[str, ...] = (),
)
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `org_id` | `UUID` | Organization identifier |
| `tenant_id` | `UUID \| None` | Tenant identifier |
| `plan_tier` | `PlanTier` | Subscription tier |
| `features` | `tuple[str, ...]` | Enabled features |

### Methods

#### `has_feature(feature: str) -> bool`

Check if feature is enabled.

### PlanTier

```python
PlanTier = Literal["starter", "pro", "enterprise"]
```

---

## Auth Interceptors

### AuthInterceptor

```python
from stageflow.auth import AuthInterceptor
```

Validates JWT tokens and creates AuthContext.

**Priority:** 1

```python
from stageflow.auth import AuthInterceptor, JwtValidator

class MyValidator:
    async def validate(self, token: str) -> AuthContext:
        # Validate and return AuthContext
        ...

auth = AuthInterceptor(validator=MyValidator())
```

### OrgEnforcementInterceptor

```python
from stageflow.auth import OrgEnforcementInterceptor
```

Ensures tenant isolation by verifying org_id matches.

**Priority:** 2

### JwtValidator Protocol

```python
from stageflow.auth import JwtValidator

class JwtValidator(Protocol):
    async def validate(self, token: str) -> AuthContext:
        """Validate JWT and return AuthContext."""
        ...
```

### MockJwtValidator

```python
from stageflow.auth import MockJwtValidator

validator = MockJwtValidator(
    user_id=uuid4(),
    org_id=uuid4(),
    roles=("user",),
)
```

Mock validator for testing.

---

## Auth Errors

```python
from stageflow.auth import (
    AuthenticationError,
    InvalidTokenError,
    TokenExpiredError,
    MissingClaimsError,
    CrossTenantAccessError,
)
```

| Error | Description |
|-------|-------------|
| `AuthenticationError` | Base authentication error |
| `InvalidTokenError` | Token is invalid |
| `TokenExpiredError` | Token has expired |
| `MissingClaimsError` | Required claims missing |
| `CrossTenantAccessError` | Cross-tenant access attempt |

---

## Auth Events

The auth system emits events for auditing:

```python
from stageflow.auth import (
    AuthLoginEvent,
    AuthFailureEvent,
    TenantAccessDeniedEvent,
)
```

| Event | Description |
|-------|-------------|
| `AuthLoginEvent` | Successful authentication |
| `AuthFailureEvent` | Failed authentication |
| `TenantAccessDeniedEvent` | Cross-tenant access blocked |

---

## Telemetry & Streaming Hooks

Authentication stages often run before any LLM/tool work but still benefit from the standard telemetry primitives:

- Wire streaming helpers (for voice/STT logins) through the execution context so auth failures can be correlated with audio queue health.
- Emit analytics overflow warnings whenever audit exporters fall behind.

```python
from stageflow.helpers import ChunkQueue, StreamingBuffer, BufferedExporter

def build_auth_telemetry(ctx):
    queue = ChunkQueue(event_emitter=ctx.try_emit_event)
    buffer = StreamingBuffer(event_emitter=ctx.try_emit_event)

    exporter = BufferedExporter(
        sink=auth_audit_sink,
        on_overflow=lambda dropped, size: ctx.try_emit_event(
            "auth.analytics.overflow",
            {"dropped": dropped, "buffer_size": size},
        ),
        high_water_mark=0.7,
    )
    return queue, buffer, exporter
```

Emitted events follow the same `stream.*` schema described in the observability guide (`stream.chunk_dropped`, `stream.producer_blocked`, `stream.throttle_started`, `stream.buffer_overflow`, `stream.buffer_underrun`, etc.).

---

## Multi-Tenant Patterns

## Usage Example

```python
from uuid import uuid4
from stageflow.auth import (
    AuthContext,
    OrgContext,
    AuthInterceptor,
    OrgEnforcementInterceptor,
    MockJwtValidator,
    CrossTenantAccessError,
)
from stageflow import get_default_interceptors

# Create auth context
auth_context = getattr(ctx.inputs.ports, "auth", None) if ctx.inputs.ports else None
auth = AuthContext(
    user_id=uuid4(),
    session_id=uuid4(),
    email="user@example.com",
    org_id=uuid4(),
    roles=("user", "editor"),
)

# Check permissions
if auth.has_role("admin"):
    print("Admin access")
if auth.is_admin():
    print("Has admin privileges")

# Create org context
org = OrgContext(
    org_id=uuid4(),
    plan_tier="pro",
    features=("advanced_analytics", "custom_models"),
)

if org.has_feature("advanced_analytics"):
    print("Analytics enabled")

# Use auth interceptors
interceptors = get_default_interceptors(include_auth=True)

# Or manually configure
validator = MockJwtValidator(user_id=uuid4(), org_id=uuid4())
auth_interceptor = AuthInterceptor(validator=validator)
org_interceptor = OrgEnforcementInterceptor()

# Handle auth errors
try:
    # ... pipeline execution
    pass
except CrossTenantAccessError as e:
    print(f"Access denied: {e}")
```
