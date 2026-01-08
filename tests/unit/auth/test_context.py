"""Unit tests for AuthContext and OrgContext."""

from uuid import UUID, uuid4

import pytest

from stageflow.auth.context import AuthContext, OrgContext


class TestAuthContext:
    """Tests for AuthContext dataclass."""

    def test_create_valid_context(self):
        """Test creating a valid AuthContext."""
        user_id = uuid4()
        session_id = uuid4()
        org_id = uuid4()

        ctx = AuthContext(
            user_id=user_id,
            session_id=session_id,
            email="user@example.com",
            org_id=org_id,
            roles=("admin", "user"),
        )

        assert ctx.user_id == user_id
        assert ctx.session_id == session_id
        assert ctx.email == "user@example.com"
        assert ctx.org_id == org_id
        assert ctx.roles == ("admin", "user")

    def test_create_minimal_context(self):
        """Test creating AuthContext with minimal required fields."""
        user_id = uuid4()
        session_id = uuid4()

        ctx = AuthContext(user_id=user_id, session_id=session_id)

        assert ctx.user_id == user_id
        assert ctx.session_id == session_id
        assert ctx.email is None
        assert ctx.org_id is None
        assert ctx.roles == ()

    def test_has_role_returns_true(self):
        """Test has_role() returns True for existing role."""
        ctx = AuthContext(
            user_id=uuid4(),
            session_id=uuid4(),
            roles=("admin", "editor"),
        )

        assert ctx.has_role("admin") is True
        assert ctx.has_role("editor") is True

    def test_has_role_returns_false(self):
        """Test has_role() returns False for missing role."""
        ctx = AuthContext(
            user_id=uuid4(),
            session_id=uuid4(),
            roles=("user",),
        )

        assert ctx.has_role("admin") is False
        assert ctx.has_role("superuser") is False

    def test_is_admin_with_admin_role(self):
        """Test is_admin() returns True for 'admin' role."""
        ctx = AuthContext(
            user_id=uuid4(),
            session_id=uuid4(),
            roles=("admin",),
        )

        assert ctx.is_admin() is True

    def test_is_admin_with_org_admin_role(self):
        """Test is_admin() returns True for 'org_admin' role."""
        ctx = AuthContext(
            user_id=uuid4(),
            session_id=uuid4(),
            roles=("org_admin",),
        )

        assert ctx.is_admin() is True

    def test_is_admin_without_admin_role(self):
        """Test is_admin() returns False without admin roles."""
        ctx = AuthContext(
            user_id=uuid4(),
            session_id=uuid4(),
            roles=("user", "editor"),
        )

        assert ctx.is_admin() is False

    def test_is_authenticated_always_true(self):
        """Test is_authenticated property is always True."""
        ctx = AuthContext(user_id=uuid4(), session_id=uuid4())

        assert ctx.is_authenticated is True

    def test_context_is_immutable(self):
        """Test that AuthContext is frozen (immutable)."""
        ctx = AuthContext(user_id=uuid4(), session_id=uuid4())

        with pytest.raises(AttributeError):
            ctx.email = "changed@example.com"

    def test_repr_hides_email(self):
        """Test that __repr__ partially hides email."""
        ctx = AuthContext(
            user_id=uuid4(),
            session_id=uuid4(),
            email="user@example.com",
        )

        repr_str = repr(ctx)
        assert "user@example.com" not in repr_str
        assert "use***" in repr_str


class TestOrgContext:
    """Tests for OrgContext dataclass."""

    def test_create_valid_context(self):
        """Test creating a valid OrgContext."""
        org_id = uuid4()
        tenant_id = uuid4()

        ctx = OrgContext(
            org_id=org_id,
            tenant_id=tenant_id,
            plan_tier="enterprise",
            features=("feature_a", "feature_b"),
        )

        assert ctx.org_id == org_id
        assert ctx.tenant_id == tenant_id
        assert ctx.plan_tier == "enterprise"
        assert ctx.features == ("feature_a", "feature_b")

    def test_create_minimal_context(self):
        """Test creating OrgContext with minimal required fields."""
        org_id = uuid4()

        ctx = OrgContext(org_id=org_id)

        assert ctx.org_id == org_id
        assert ctx.tenant_id is None
        assert ctx.plan_tier == "starter"
        assert ctx.features == ()

    def test_has_feature_returns_true(self):
        """Test has_feature() returns True for enabled feature."""
        ctx = OrgContext(
            org_id=uuid4(),
            features=("feature_a", "feature_b"),
        )

        assert ctx.has_feature("feature_a") is True
        assert ctx.has_feature("feature_b") is True

    def test_has_feature_returns_false(self):
        """Test has_feature() returns False for disabled feature."""
        ctx = OrgContext(
            org_id=uuid4(),
            features=("feature_a",),
        )

        assert ctx.has_feature("feature_x") is False

    def test_context_is_immutable(self):
        """Test that OrgContext is frozen (immutable)."""
        ctx = OrgContext(org_id=uuid4())

        with pytest.raises(AttributeError):
            ctx.plan_tier = "enterprise"
