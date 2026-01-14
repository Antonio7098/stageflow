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

**Parameters:**
- `role`: Role name to check

**Returns:** `True` if user has the role

**Example:**
```python
auth = AuthContext(user_id=uuid4(), session_id=uuid4(), roles=("admin", "editor"))
if auth.has_role("admin"):
    print("User is admin")
```

#### `is_admin() -> bool`

Check if user has 'admin' or 'org_admin' role.

**Returns:** `True` if user has admin privileges

**Example:**
```python
if auth.is_admin():
    # Grant admin access
    pass
```

### Properties

#### `is_authenticated -> bool`

Always returns `True` for valid AuthContext.

**Example:**
```python
if auth.is_authenticated:
    print("User is authenticated")
```

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

**Parameters:**
- `feature`: Feature name to check

**Returns:** `True` if feature is enabled

**Example:**
```python
org = OrgContext(
    org_id=uuid4(),
    plan_tier="pro",
    features=("advanced_analytics", "custom_models")
)

if org.has_feature("advanced_analytics"):
    print("Analytics available")
```

### PlanTier

```python
PlanTier = Literal["starter", "pro", "enterprise"]
```

Supported subscription tiers.

---

## Auth Interceptors

### AuthInterceptor

```python
from stageflow.auth import AuthInterceptor
```

Validates JWT tokens and creates AuthContext.

**Priority:** 1 (runs first)

**Attributes:**
- `name`: `"auth"`
- `priority`: `1`

#### Constructor

```python
AuthInterceptor(jwt_validator: JwtValidator | None = None)
```

**Parameters:**
- `jwt_validator`: JWT validation implementation (defaults to MockJwtValidator)

#### Behavior

- Extracts token from `ctx.data["_auth_token"]` or `ctx.data.get("auth_token")`
- Validates token using JwtValidator
- Stores AuthContext in `ctx.data["_auth_context"]`
- Sets `ctx.data["_user_id"]` and `ctx.data["_org_id"]`
- Emits `auth.login` event on success
- Emits `auth.failure` event on failure

**Example:**
```python
from stageflow.auth import AuthInterceptor, JwtValidator

class MyValidator:
    async def validate(self, token: str) -> dict[str, Any]:
        # Validate JWT and return claims
        return {
            "user_id": "550e8400-e29b-41d4-a716-446655440000",
            "session_id": "550e8400-e29b-41d4-a716-446655440001",
            "email": "user@example.com",
            "org_id": "550e8400-e29b-41d4-a716-446655440002",
            "roles": ["user"]
        }

auth = AuthInterceptor(validator=MyValidator())
```

---

### OrgEnforcementInterceptor

```python
from stageflow.auth import OrgEnforcementInterceptor
```

Ensures tenant isolation by verifying org_id matches.

**Priority:** 2 (runs after auth)

**Attributes:**
- `name`: `"org_enforcement"`
- `priority`: `2`

#### Behavior

- Requires AuthContext to be present (AuthInterceptor must run first)
- Checks `ctx.data["_resource_org_id"]` against authenticated user's org_id
- Blocks cross-tenant access attempts
- Emits `tenant.access_denied` event on violations

**Example:**
```python
# Set resource org_id in context
ctx.data["_resource_org_id"] = resource.organization_id

# OrgEnforcementInterceptor will verify access
org_interceptor = OrgEnforcementInterceptor()
```

---

## JwtValidator Protocol

```python
from stageflow.auth import JwtValidator
```

Protocol for JWT validation implementations.

**Methods:**

#### `async validate(token: str) -> dict[str, Any]`

Validate a JWT token and return claims.

**Parameters:**
- `token`: The JWT token string

**Returns:** Dictionary of validated claims

**Raises:**
- `TokenExpiredError` - If token has expired
- `InvalidTokenError` - If token is malformed or signature invalid
- `MissingClaimsError` - If required claims are missing

**Example Implementation:**
```python
class CustomJwtValidator:
    async def validate(self, token: str) -> dict[str, Any]:
        # Validate with your JWT library
        payload = decode_jwt(token)
        
        # Extract required claims
        if not payload.get("user_id"):
            raise MissingClaimsError("Missing user_id claim", ["user_id"])
            
        return payload
```

---

## MockJwtValidator

```python
from stageflow.auth import MockJwtValidator
```

Mock JWT validator for testing and development.

**Token Format:** `"valid_<user_id>_<org_id>_<roles>"`

**Rejected Formats:**
- `"expired_*"` - Raises TokenExpiredError
- `"invalid_*"` - Raises InvalidTokenError
- `"missing_*"` - Raises MissingClaimsError

**Example:**
```python
validator = MockJwtValidator()

# Valid token
claims = await validator.validate("valid_550e8400-e29b-41d4-a716-446655440000_550e8400-e29b-41d4-a716-446655440001_admin,user")

# Expired token
try:
    await validator.validate("expired_token")
except TokenExpiredError:
    print("Token expired")
```

---

## Auth Errors

```python
from stageflow.auth import (
    AuthenticationError,
    InvalidTokenError,
    TokenExpiredError,
    MissingClaimsError,
)
```

### AuthenticationError

Base authentication error.

### InvalidTokenError

Token is malformed or signature invalid.

**Attributes:**
- `message`: Error description

### TokenExpiredError

Token has expired.

**Attributes:**
- `message`: Error description

### MissingClaimsError

Required claims are missing from token.

**Attributes:**
- `message`: Error description
- `missing_claims`: List of missing claim names

**Example:**
```python
try:
    claims = await validator.validate(token)
except MissingClaimsError as e:
    print(f"Missing claims: {e.missing_claims}")
```

---

## Auth Events

The auth system emits events for auditing and monitoring.

```python
from stageflow.auth import (
    AuthLoginEvent,
    AuthFailureEvent,
    TenantAccessDeniedEvent,
)
```

### AuthLoginEvent

Emitted on successful authentication.

**Attributes:**
- `user_id`: User identifier
- `session_id`: Session identifier
- `org_id`: Organization identifier (optional)
- `request_id`: Request identifier
- `pipeline_run_id`: Pipeline run identifier

### AuthFailureEvent

Emitted on authentication failure.

**Attributes:**
- `reason`: Failure reason (e.g., "missing_token", "invalid_token")
- `request_id`: Request identifier
- `ip_address`: Client IP address (optional)
- `user_agent`: User agent string (optional)

### TenantAccessDeniedEvent

Emitted when cross-tenant access is blocked.

**Attributes:**
- `user_org_id`: User's organization ID
- `resource_org_id`: Resource's organization ID
- `user_id`: User identifier
- `request_id`: Request identifier
- `pipeline_run_id`: Pipeline run identifier

---

## Usage Examples

### Complete Auth Setup

```python
from uuid import uuid4
from stageflow.auth import (
    AuthContext,
    OrgContext,
    AuthInterceptor,
    OrgEnforcementInterceptor,
    MockJwtValidator,
)
from stageflow import Pipeline, StageKind

# Create auth components
validator = MockJwtValidator()
auth_interceptor = AuthInterceptor(validator)
org_interceptor = OrgEnforcementInterceptor()

# Build pipeline with auth interceptors
pipeline = (
    Pipeline()
    .with_stage("protected_stage", MyStage(), StageKind.TRANSFORM)
)

# Run with interceptors
interceptors = [auth_interceptor, org_interceptor]
graph = pipeline.build()
results = await graph.run(ctx, interceptors=interceptors)
```

### Manual Auth Context Creation

```python
# Create auth context manually (for testing or service accounts)
auth = AuthContext(
    user_id=uuid4(),
    session_id=uuid4(),
    email="user@example.com",
    org_id=uuid4(),
    roles=("user", "editor"),
)

# Check permissions
if auth.has_role("admin"):
    print("Admin access granted")
if auth.is_admin():
    print("Has admin privileges")

# Create org context
org = OrgContext(
    org_id=uuid4(),
    plan_tier="pro",
    features=("advanced_analytics", "custom_models"),
)

if org.has_feature("advanced_analytics"):
    print("Analytics feature available")
```

### Custom JWT Validator

```python
import jwt
from stageflow.auth import JwtValidator, TokenExpiredError, InvalidTokenError

class MyJwtValidator(JwtValidator):
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
    
    async def validate(self, token: str) -> dict[str, Any]:
        try:
            # Decode and validate JWT
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"],
                options={"require": ["exp", "user_id", "session_id"]}
            )
            
            # Check expiration
            if payload["exp"] < datetime.now().timestamp():
                raise TokenExpiredError("Token has expired")
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Token has expired")
        except jwt.InvalidTokenError:
            raise InvalidTokenError("Invalid token")
        except KeyError as e:
            raise MissingClaimsError(f"Missing claim: {e}", [str(e)])

# Use custom validator
auth_interceptor = AuthInterceptor(MyJwtValidator("your-secret-key"))
```

### Resource Access Control

```python
# In a stage that accesses resources
async def execute(self, ctx: StageContext) -> StageOutput:
    # Get resource from database
    resource = await get_resource(resource_id)
    
    # Set resource org_id for enforcement
    ctx.data["_resource_org_id"] = resource.organization_id
    
    # OrgEnforcementInterceptor will verify access
    # before this stage executes
    
    return StageOutput.ok(resource=resource)
```

---

## Best Practices

1. **Always use AuthInterceptor first** - Set priority=1 to ensure auth runs before other logic
2. **Implement proper JWT validation** - Use production-ready JWT libraries
3. **Use org enforcement for multi-tenant apps** - Prevent cross-tenant data access
4. **Log auth events** - Monitor for suspicious activity patterns
5. **Validate token format** - Ensure UUIDs are properly formatted
6. **Handle auth errors gracefully** - Provide clear error messages to users
7. **Use mock validator for testing** - Simplify unit test setup
