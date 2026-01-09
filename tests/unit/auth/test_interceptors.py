"""Unit tests for AuthInterceptor and OrgEnforcementInterceptor."""

from uuid import uuid4

import pytest

from stageflow.auth.context import AuthContext
from stageflow.auth.interceptors import (
    AuthInterceptor,
    MockJwtValidator,
    OrgEnforcementInterceptor,
)
from stageflow.events import NoOpEventSink
from stageflow.stages.context import PipelineContext


def create_test_context(**kwargs) -> PipelineContext:
    """Create a PipelineContext for testing."""
    defaults = {
        "pipeline_run_id": uuid4(),
        "request_id": uuid4(),
        "session_id": uuid4(),
        "user_id": None,
        "org_id": None,
        "interaction_id": None,
        "event_sink": NoOpEventSink(),
    }
    defaults.update(kwargs)
    return PipelineContext(**defaults)


class TestMockJwtValidator:
    """Tests for MockJwtValidator."""

    @pytest.mark.asyncio
    async def test_valid_token(self):
        """Test validating a valid token with UUIDs."""
        validator = MockJwtValidator()
        user_uuid = "00000000-0000-0000-0000-000000000001"
        org_uuid = "00000000-0000-0000-0000-000000000002"
        claims = await validator.validate(f"valid_{user_uuid}_{org_uuid}_admin,user")

        assert claims["user_id"] == user_uuid
        assert claims["org_id"] == org_uuid
        assert claims["roles"] == ("admin", "user")

    @pytest.mark.asyncio
    async def test_expired_token(self):
        """Test validating an expired token."""
        from stageflow.auth.errors import TokenExpiredError

        validator = MockJwtValidator()
        with pytest.raises(TokenExpiredError):
            await validator.validate("expired_token")

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        """Test validating an invalid token."""
        from stageflow.auth.errors import InvalidTokenError

        validator = MockJwtValidator()
        with pytest.raises(InvalidTokenError):
            await validator.validate("invalid_token")

    @pytest.mark.asyncio
    async def test_missing_claims_token(self):
        """Test validating a token with missing claims."""
        from stageflow.auth.errors import MissingClaimsError

        validator = MockJwtValidator()
        with pytest.raises(MissingClaimsError):
            await validator.validate("missing_claims_token")


class TestAuthInterceptor:
    """Tests for AuthInterceptor."""

    @pytest.mark.asyncio
    async def test_before_with_valid_token(self):
        """Test before() with valid token creates AuthContext."""
        interceptor = AuthInterceptor()
        ctx = create_test_context()
        user_uuid = "00000000-0000-0000-0000-000000000001"
        org_uuid = "00000000-0000-0000-0000-000000000002"
        ctx.data["_auth_token"] = f"valid_{user_uuid}_{org_uuid}_admin"

        result = await interceptor.before("test_stage", ctx)

        assert result is None  # No short-circuit
        assert "_auth_context" in ctx.data
        auth_ctx: AuthContext = ctx.data["_auth_context"]
        assert isinstance(auth_ctx, AuthContext)

    @pytest.mark.asyncio
    async def test_before_with_missing_token(self):
        """Test before() with missing token returns error."""
        interceptor = AuthInterceptor()
        ctx = create_test_context()

        result = await interceptor.before("test_stage", ctx)

        assert result is not None
        assert result.stage_ran is False
        assert "missing" in result.error.lower()

    @pytest.mark.asyncio
    async def test_before_with_expired_token(self):
        """Test before() with expired token returns error."""
        interceptor = AuthInterceptor()
        ctx = create_test_context()
        ctx.data["_auth_token"] = "expired_token"

        result = await interceptor.before("test_stage", ctx)

        assert result is not None
        assert result.stage_ran is False
        assert "expired" in result.error.lower()

    @pytest.mark.asyncio
    async def test_before_with_invalid_token(self):
        """Test before() with invalid token returns error."""
        interceptor = AuthInterceptor()
        ctx = create_test_context()
        ctx.data["_auth_token"] = "invalid_token"

        result = await interceptor.before("test_stage", ctx)

        assert result is not None
        assert result.stage_ran is False
        assert "invalid" in result.error.lower()

    @pytest.mark.asyncio
    async def test_before_sets_user_and_org_ids(self):
        """Test before() sets user_id and org_id in context data."""
        interceptor = AuthInterceptor()
        ctx = create_test_context()
        user_uuid = "00000000-0000-0000-0000-000000000001"
        org_uuid = "00000000-0000-0000-0000-000000000002"
        ctx.data["_auth_token"] = f"valid_{user_uuid}_{org_uuid}_"

        await interceptor.before("test_stage", ctx)

        assert "_user_id" in ctx.data
        assert "_org_id" in ctx.data

    @pytest.mark.asyncio
    async def test_priority_is_1(self):
        """Test that AuthInterceptor has priority 1."""
        interceptor = AuthInterceptor()
        assert interceptor.priority == 1

    @pytest.mark.asyncio
    async def test_name_is_auth(self):
        """Test that AuthInterceptor has name 'auth'."""
        interceptor = AuthInterceptor()
        assert interceptor.name == "auth"


class TestOrgEnforcementInterceptor:
    """Tests for OrgEnforcementInterceptor."""

    @pytest.mark.asyncio
    async def test_before_allows_same_org_access(self):
        """Test before() allows access when org_ids match."""
        interceptor = OrgEnforcementInterceptor()
        ctx = create_test_context()

        org_id = uuid4()
        ctx.data["_auth_context"] = AuthContext(
            user_id=uuid4(),
            session_id=uuid4(),
            org_id=org_id,
        )
        ctx.data["_resource_org_id"] = org_id

        result = await interceptor.before("test_stage", ctx)

        assert result is None  # Access allowed

    @pytest.mark.asyncio
    async def test_before_denies_different_org_access(self):
        """Test before() denies access when org_ids differ."""
        interceptor = OrgEnforcementInterceptor()
        ctx = create_test_context()

        user_org_id = uuid4()
        resource_org_id = uuid4()
        ctx.data["_auth_context"] = AuthContext(
            user_id=uuid4(),
            session_id=uuid4(),
            org_id=user_org_id,
        )
        ctx.data["_resource_org_id"] = resource_org_id

        result = await interceptor.before("test_stage", ctx)

        assert result is not None
        assert result.stage_ran is False
        assert "cross-tenant" in result.error.lower() or "denied" in result.error.lower()

    @pytest.mark.asyncio
    async def test_before_allows_when_no_resource_org(self):
        """Test before() allows access when no resource org_id is set."""
        interceptor = OrgEnforcementInterceptor()
        ctx = create_test_context()

        ctx.data["_auth_context"] = AuthContext(
            user_id=uuid4(),
            session_id=uuid4(),
            org_id=uuid4(),
        )
        # No _resource_org_id set

        result = await interceptor.before("test_stage", ctx)

        assert result is None  # Access allowed

    @pytest.mark.asyncio
    async def test_before_fails_without_auth_context(self):
        """Test before() fails when AuthContext is missing."""
        interceptor = OrgEnforcementInterceptor()
        ctx = create_test_context()
        # No _auth_context set

        result = await interceptor.before("test_stage", ctx)

        assert result is not None
        assert result.stage_ran is False
        assert "authcontext" in result.error.lower()

    @pytest.mark.asyncio
    async def test_priority_is_2(self):
        """Test that OrgEnforcementInterceptor has priority 2."""
        interceptor = OrgEnforcementInterceptor()
        assert interceptor.priority == 2

    @pytest.mark.asyncio
    async def test_name_is_org_enforcement(self):
        """Test that OrgEnforcementInterceptor has name 'org_enforcement'."""
        interceptor = OrgEnforcementInterceptor()
        assert interceptor.name == "org_enforcement"

    @pytest.mark.asyncio
    async def test_before_handles_string_resource_org_id(self):
        """Test before() handles string resource_org_id."""
        interceptor = OrgEnforcementInterceptor()
        ctx = create_test_context()

        org_id = uuid4()
        ctx.data["_auth_context"] = AuthContext(
            user_id=uuid4(),
            session_id=uuid4(),
            org_id=org_id,
        )
        ctx.data["_resource_org_id"] = str(org_id)  # String instead of UUID

        result = await interceptor.before("test_stage", ctx)

        assert result is None  # Access allowed
