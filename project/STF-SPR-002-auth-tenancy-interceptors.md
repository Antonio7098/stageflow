# STF-SPR-002: Auth + Tenancy Interceptors

**Status:** 🟢 Complete  
**Branch:** `feature/stf-spr-002-auth-tenancy-interceptors`  
**Duration:** 1 week  
**Dependencies:** STF-SPR-001 (Pipeline Composition)

---

## 📅 Sprint Details & Goals

### Overview
Implement authentication and tenancy enforcement interceptors for the stageflow framework. These interceptors run before any stage logic to validate JWT tokens and enforce org isolation.

### Primary Goal (Must-Have)
- **AuthInterceptor validates JWT → AuthContext with user_id, org_id, roles**
- **OrgEnforcementInterceptor denies cross-tenant access attempts**
- **All resources validate `org_id` matches AuthContext**

### Success Criteria
- [x] `AuthInterceptor` validates JWT tokens (Clerk/WorkOS)
- [x] `AuthContext` dataclass with user_id, org_id, roles, session_id
- [x] `OrgEnforcementInterceptor` enforces tenant isolation
- [x] Cross-tenant access returns 403 and logs audit event
- [x] Integration tests for auth flows pass

---

## 🏗️ Architecture & Design

### AuthContext Design

```python
@dataclass(frozen=True, slots=True)
class AuthContext:
    """Authenticated user context from JWT validation."""
    user_id: UUID
    email: str | None
    org_id: UUID | None
    roles: tuple[str, ...]
    session_id: UUID
    
    def has_role(self, role: str) -> bool:
        return role in self.roles
    
    def is_admin(self) -> bool:
        return self.has_role("admin") or self.has_role("org_admin")
```

### AuthInterceptor Design

```python
class AuthInterceptor(BaseInterceptor):
    """Validates JWT and populates AuthContext."""
    
    name = "auth"
    priority = 1  # Runs first (before circuit breaker)
    
    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        token = ctx.data.get("_auth_token")
        if not token:
            return InterceptorResult(
                stage_ran=False,
                error="Missing authentication token",
            )
        
        try:
            auth_context = await self._validate_token(token)
            ctx.data["_auth_context"] = auth_context
            ctx.user_id = auth_context.user_id
            ctx.org_id = auth_context.org_id
        except AuthenticationError as e:
            await self._emit_auth_failure(ctx, e)
            return InterceptorResult(stage_ran=False, error=str(e))
        
        return None
    
    async def _validate_token(self, token: str) -> AuthContext:
        """Validate JWT with Clerk/WorkOS."""
        ...
```

### OrgEnforcementInterceptor Design

```python
class OrgEnforcementInterceptor(BaseInterceptor):
    """Enforces tenant isolation on all resource access."""
    
    name = "org_enforcement"
    priority = 2  # Runs after auth
    
    async def before(self, stage_name: str, ctx: PipelineContext) -> InterceptorResult | None:
        auth_context = ctx.data.get("_auth_context")
        if not auth_context:
            return InterceptorResult(
                stage_ran=False,
                error="AuthContext not available",
            )
        
        # Check if stage accesses resources with different org_id
        resource_org_id = ctx.data.get("_resource_org_id")
        if resource_org_id and resource_org_id != auth_context.org_id:
            await self._emit_tenant_violation(ctx, auth_context, resource_org_id)
            return InterceptorResult(
                stage_ran=False,
                error="Cross-tenant access denied",
            )
        
        return None
```

### Interceptor Chain Order

```
Request
   │
   ├── 1. AuthInterceptor (priority=1)
   │       └── Validate JWT → AuthContext
   │
   ├── 2. OrgEnforcementInterceptor (priority=2)
   │       └── Enforce org_id isolation
   │
   ├── 3. TimeoutInterceptor (priority=5)
   │
   ├── 4. CircuitBreakerInterceptor (priority=10)
   │
   ├── 5. TracingInterceptor (priority=20)
   │
   ├── 6. MetricsInterceptor (priority=40)
   │
   └── 7. LoggingInterceptor (priority=50)
           └── Stage execution
```

---

## 🧩 Parallelization Plan (A/B)

### Worker A (Auth)
**Owns:** JWT validation and AuthContext

- **Task 1.1:** Create `AuthContext` dataclass
- **Task 1.2:** Create `AuthInterceptor` with JWT validation
- **Task 1.3:** Integrate with Clerk/WorkOS JWT verification
- **Task 1.4:** Unit tests for token validation
- **Task 1.5:** Integration tests for auth flows

**Produces:** G2 (partial)

### Worker B (Tenancy)
**Owns:** Org isolation enforcement

- **Task 2.1:** Create `OrgEnforcementInterceptor`
- **Task 2.2:** Implement cross-tenant detection logic
- **Task 2.3:** Create audit events for violations
- **Task 2.4:** Update default interceptor chain
- **Task 2.5:** Integration tests for cross-tenant denial

**Produces:** G2 (partial)

### Gates

- **G2 (Tenancy Enforcement):**
  - [x] Worker A: AuthInterceptor validates JWT
  - [x] Worker B: OrgEnforcementInterceptor denies cross-tenant
  - [x] Both: Integration tests pass

---

## ✅ Detailed Task List

### Setup & Infrastructure
- [x] **Task 0.1: Create auth module structure**
  - [x] Create directory `stageflow/auth/`
  - [x] Create `stageflow/auth/__init__.py` with module exports
  - [x] Create `stageflow/auth/context.py` for AuthContext
  - [x] Create `stageflow/auth/errors.py` for auth exceptions

- [x] **Task 0.2: Review existing auth code**
  - [x] Document current auth flow for reference

### AuthContext Model (Worker A)
- [x] **Task 1.1: Create AuthContext dataclass**
  - [x] Create file `stageflow/auth/context.py`
  - [x] Define `AuthContext` dataclass with fields: `user_id`, `email`, `org_id`, `roles`, `session_id`
  - [x] Use `UUID` for `user_id`, `org_id`, `session_id`
  - [x] Use `tuple[str, ...]` for `roles` (immutable)
  - [x] Add `@dataclass(frozen=True, slots=True)` for immutability and performance

- [x] **Task 1.2: Add AuthContext helper methods**
  - [x] Add `has_role(role: str) -> bool` method
  - [x] Add `is_admin() -> bool` method (checks for "admin" or "org_admin")
  - [x] Add `is_authenticated() -> bool` property (always True for valid AuthContext)
  - [x] Add `__repr__` that hides sensitive data

- [x] **Task 1.3: Create OrgContext dataclass**
  - [x] Define `OrgContext` dataclass with fields: `org_id`, `tenant_id`, `plan_tier`, `features`
  - [x] Use `Literal["starter", "pro", "enterprise"]` for `plan_tier`
  - [x] Use `tuple[str, ...]` for `features`
  - [x] Add `has_feature(feature: str) -> bool` method

- [x] **Task 1.4: Create auth exceptions**
  - [x] Create file `stageflow/auth/errors.py`
  - [x] Define `AuthenticationError` base exception
  - [x] Define `TokenExpiredError(AuthenticationError)`
  - [x] Define `InvalidTokenError(AuthenticationError)`
  - [x] Define `MissingClaimsError(AuthenticationError)`
  - [x] Define `CrossTenantAccessError(AuthenticationError)`

- [x] **Task 1.5: Unit tests for AuthContext**
  - [x] Create file `tests/unit/auth/test_context.py`
  - [x] Test AuthContext creation with valid data
  - [x] Test has_role() returns correct boolean
  - [x] Test is_admin() for various role combinations
  - [x] Test AuthContext is immutable (frozen)

### AuthInterceptor (Worker A)
- [x] **Task 2.1: Create BaseInterceptor if not exists**
  - [x] Check if `stageflow/pipeline/interceptors.py` has BaseInterceptor
  - [x] If not, create `BaseInterceptor` Protocol with `before()`, `after()`, `on_error()` methods
  - [x] Add `name: str` and `priority: int` attributes

- [x] **Task 2.2: Create AuthInterceptor class**
  - [x] Create `AuthInterceptor(BaseInterceptor)` class in `stageflow/auth/interceptors.py`
  - [x] Set `name = "auth"` and `priority = 1` (runs first)
  - [x] Add `jwt_validator` dependency for token validation
  - [x] Add `__init__` to accept validator configuration

- [x] **Task 2.3: Implement AuthInterceptor.before() method**
  - [x] Get token from `ctx.data.get("_auth_token")` or HTTP header
  - [x] If no token, return `InterceptorResult(stage_ran=False, error="Missing authentication token")`
  - [x] Call `_validate_token(token)` to get AuthContext
  - [x] Store AuthContext in `ctx.data["_auth_context"]`
  - [x] Set `ctx.user_id` and `ctx.org_id` from AuthContext
  - [x] On validation failure, emit `auth.failure` event and return error

- [x] **Task 2.4: Implement _validate_token() method**
  - [x] Decode JWT using Clerk/WorkOS SDK
  - [x] Extract `user_id`, `email`, `org_id` from claims
  - [x] Extract `roles` from custom claims or metadata
  - [x] Create and return `AuthContext` instance
  - [x] Raise appropriate exception on failure

- [x] **Task 2.5: Add JWT validation integration**
  - [x] Create `JwtValidator` Protocol with `validate(token: str) -> dict`
  - [x] Create `ClerkJwtValidator` implementation
  - [x] Create `WorkOSJwtValidator` implementation
  - [x] Add configuration to select validator based on env

- [x] **Task 2.6: Unit tests for AuthInterceptor**
  - [x] Create file `tests/unit/auth/test_interceptor.py`
  - [x] Test before() with valid token creates AuthContext
  - [x] Test before() with missing token returns error
  - [x] Test before() with expired token returns error
  - [x] Test before() with invalid signature returns error
  - [x] Test before() emits auth.failure event on error

### OrgEnforcementInterceptor (Worker B)
- [x] **Task 3.1: Create OrgEnforcementInterceptor class**
  - [x] Create `OrgEnforcementInterceptor(BaseInterceptor)` class in `stageflow/auth/interceptors.py`
  - [x] Set `name = "org_enforcement"` and `priority = 2` (runs after auth)

- [x] **Task 3.2: Implement before() method**
  - [x] Get AuthContext from `ctx.data.get("_auth_context")`
  - [x] If no AuthContext, return error (auth interceptor should have run first)
  - [x] Get resource org_id from `ctx.data.get("_resource_org_id")`
  - [x] If resource org_id exists and differs from AuthContext.org_id, deny access
  - [x] Emit `tenant.access_denied` event on violation
  - [x] Return `InterceptorResult(stage_ran=False, error="Cross-tenant access denied")`

- [x] **Task 3.3: Add resource org_id pattern**
  - [x] Document pattern: stages set `ctx.data["_resource_org_id"]` before accessing resources
  - [x] Create helper: `ctx.set_resource_org_id(org_id: UUID)`
  - [x] Create helper: `ctx.validate_resource_access(resource_org_id: UUID)`

- [x] **Task 3.4: Unit tests for OrgEnforcementInterceptor**
  - [x] Create file `tests/unit/auth/test_org_interceptor.py`
  - [x] Test before() allows same org_id access
  - [x] Test before() denies different org_id access
  - [x] Test before() allows when no resource org_id set
  - [x] Test before() emits tenant.access_denied event

### Interceptor Chain Integration (Worker B)
- [x] **Task 4.1: Update get_default_interceptors()**
  - [x] Update `stageflow/pipeline/interceptors.py`
  - [x] Add AuthInterceptor with priority 1
  - [x] Add OrgEnforcementInterceptor with priority 2
  - [x] Ensure interceptors are sorted by priority

- [x] **Task 4.2: Update PipelineOrchestrator to use interceptors**
  - [x] Verify orchestrator calls interceptors in priority order

- [x] **Task 4.3: Integration tests for interceptor chain**
  - [x] Create file `tests/integration/test_auth_chain.py`
  - [x] Test full auth flow: valid token → AuthContext → stage execution
  - [x] Test invalid token stops pipeline with 401
  - [x] Test cross-tenant access stops pipeline with 403
  - [x] Test interceptor order is respected

### Audit Events (Worker B)
- [x] **Task 5.1: Define audit event types**
  - [x] Create file `stageflow/auth/events.py`
  - [x] Define `AuthLoginEvent` with `user_id`, `org_id`, `session_id`
  - [x] Define `AuthFailureEvent` with `reason`, `ip_address`, `user_agent`
  - [x] Define `TenantAccessDeniedEvent` with `user_org_id`, `resource_org_id`

- [x] **Task 5.2: Implement event emission**
  - [x] Emit `auth.login` on successful authentication
  - [x] Emit `auth.failure` on authentication failure
  - [x] Emit `tenant.access_denied` on cross-tenant violation
  - [x] Include `request_id` and `pipeline_run_id` in all events

- [x] **Task 5.3: Add audit event tests**
  - [x] Create file `tests/unit/auth/test_events.py`

### Documentation
- [x] **Task 6.1: Document interceptor chain in ARCHITECTURE.md**
  - [x] Add "Authentication & Authorization" section
  - [x] Document interceptor priority order
  - [x] Include sequence diagram for auth flow
  - [x] Document AuthContext fields and usage

- [x] **Task 6.2: Add security audit logging guide**
  - [x] Create `docs/guides/security-audit-logging.md`
  - [x] Document all audit events and their triggers
  - [x] Document retention policy recommendations
  - [x] Include compliance considerations (GDPR, SOC2)

---

## 🔍 Test Plan

### Unit Tests
| Component | Test File | Coverage |
|-----------|-----------|----------|
| AuthContext | `tests/unit/framework/test_auth_context.py` | 100% |
| AuthInterceptor | `tests/unit/framework/test_auth_interceptor.py` | >90% |
| OrgEnforcementInterceptor | `tests/unit/framework/test_org_interceptor.py` | >90% |

### Integration Tests
| Flow | Test File | Services Mocked |
|------|-----------|-----------------|
| Valid JWT → AuthContext | `tests/integration/test_auth_flow.py` | JWT provider |
| Invalid JWT → 401 | `tests/integration/test_auth_flow.py` | JWT provider |
| Cross-tenant → 403 | `tests/integration/test_tenancy.py` | None |

---

## 👁️ Observability Checklist

### Audit Events (Mandatory)
- [x] `auth.login` — successful authentication
- [x] `auth.failure` — failed authentication (invalid token, expired, etc.)
- [x] `tenant.access_denied` — cross-tenant access attempt

### Event Schema
```json
{
  "type": "auth.failure",
  "timestamp": "ISO8601",
  "request_id": "uuid",
  "user_id": "uuid | null",
  "org_id": "uuid | null",
  "reason": "token_expired | invalid_signature | missing_claims",
  "ip_address": "string",
  "user_agent": "string"
}
```

---

## ✔️ Completion Checklist

- [x] AuthInterceptor validates JWT
- [x] AuthContext populated on PipelineContext
- [x] OrgEnforcementInterceptor denies cross-tenant
- [x] Audit events emitted
- [x] Tests passing
- [x] Docs updated

---

## 🔗 Related Documents

- [stageflow2.md](./stageflow2.md) §11 Security, Tenancy, and Residency
- [MASTER-ROADMAP.md](../MASTER-ROADMAP.md) — Gate G2
- [ENT-SPR-002](../salewind-sprints/ENT-SPR-002-org-tenancy-primitives.md) — Org primitives
