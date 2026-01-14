"""Tests for multi-tenant isolation utilities."""

from uuid import uuid4

import pytest

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


class TestTenantContext:
    """Tests for TenantContext."""

    def test_validate_access_same_tenant(self):
        """Access to same tenant resources is allowed."""
        org_id = uuid4()
        ctx = TenantContext(org_id=org_id)

        # Should not raise
        ctx.validate_access(org_id, operation="read_document")

    def test_validate_access_different_tenant(self):
        """Access to different tenant resources is blocked."""
        org_id = uuid4()
        other_org_id = uuid4()
        ctx = TenantContext(org_id=org_id)

        with pytest.raises(TenantIsolationError) as exc_info:
            ctx.validate_access(other_org_id, operation="read_document")

        assert exc_info.value.expected_org_id == org_id
        assert exc_info.value.actual_org_id == other_org_id
        assert exc_info.value.operation == "read_document"

    def test_validate_access_shared_resource(self):
        """Access to shared resources (None org_id) is allowed."""
        org_id = uuid4()
        ctx = TenantContext(org_id=org_id)

        # Should not raise - shared resource
        ctx.validate_access(None, operation="read_shared")

    def test_to_dict(self):
        """to_dict returns all context fields."""
        org_id = uuid4()
        user_id = uuid4()
        session_id = uuid4()
        ctx = TenantContext(
            org_id=org_id,
            user_id=user_id,
            session_id=session_id,
            metadata={"key": "value"},
        )

        result = ctx.to_dict()

        assert result["org_id"] == str(org_id)
        assert result["user_id"] == str(user_id)
        assert result["session_id"] == str(session_id)
        assert result["metadata"] == {"key": "value"}

    def test_from_snapshot(self):
        """from_snapshot creates TenantContext from ContextSnapshot."""
        from stageflow.context import ContextSnapshot
        from stageflow.context.identity import RunIdentity

        org_id = uuid4()
        user_id = uuid4()
        session_id = uuid4()

        snapshot = ContextSnapshot(
            run_id=RunIdentity(
                org_id=org_id,
                user_id=user_id,
                session_id=session_id,
            )
        )

        ctx = TenantContext.from_snapshot(snapshot)

        assert ctx is not None
        assert ctx.org_id == org_id
        assert ctx.user_id == user_id
        assert ctx.session_id == session_id

    def test_from_snapshot_no_org_id(self):
        """from_snapshot returns None if no org_id."""
        from stageflow.context import ContextSnapshot

        snapshot = ContextSnapshot()
        ctx = TenantContext.from_snapshot(snapshot)

        assert ctx is None

    def test_get_logger(self):
        """get_logger returns TenantAwareLogger."""
        org_id = uuid4()
        ctx = TenantContext(org_id=org_id)

        logger = ctx.get_logger("test_module")

        assert isinstance(logger, TenantAwareLogger)


class TestTenantIsolationValidator:
    """Tests for TenantIsolationValidator."""

    def test_record_access_same_tenant(self):
        """Access to same tenant is allowed and tracked."""
        org_id = uuid4()
        validator = TenantIsolationValidator(expected_org_id=org_id)

        result = validator.record_access(org_id, resource_type="document")

        assert result is True
        assert validator.is_isolated()
        assert org_id in validator.get_accessed_tenants()

    def test_record_access_different_tenant_strict(self):
        """Access to different tenant raises in strict mode."""
        org_id = uuid4()
        other_org_id = uuid4()
        validator = TenantIsolationValidator(expected_org_id=org_id, strict=True)

        with pytest.raises(TenantIsolationError):
            validator.record_access(other_org_id, resource_type="document")

    def test_record_access_different_tenant_non_strict(self):
        """Access to different tenant is recorded in non-strict mode."""
        org_id = uuid4()
        other_org_id = uuid4()
        validator = TenantIsolationValidator(expected_org_id=org_id, strict=False)

        result = validator.record_access(other_org_id, resource_type="document")

        assert result is False
        assert not validator.is_isolated()
        violations = validator.get_violations()
        assert len(violations) == 1
        assert violations[0]["actual_org_id"] == str(other_org_id)

    def test_record_access_shared_resource(self):
        """Access to shared resources (None org_id) is always allowed."""
        org_id = uuid4()
        validator = TenantIsolationValidator(expected_org_id=org_id)

        result = validator.record_access(None, resource_type="shared_config")

        assert result is True
        assert validator.is_isolated()

    def test_multiple_accesses_tracked(self):
        """Multiple accesses to same tenant are tracked."""
        org_id = uuid4()
        validator = TenantIsolationValidator(expected_org_id=org_id)

        validator.record_access(org_id, resource_type="doc1", resource_id="1")
        validator.record_access(org_id, resource_type="doc2", resource_id="2")
        validator.record_access(org_id, resource_type="doc3", resource_id="3")

        accessed = validator.get_accessed_tenants()
        assert len(accessed) == 1
        assert org_id in accessed

    def test_get_violations_empty(self):
        """get_violations returns empty list when no violations."""
        org_id = uuid4()
        validator = TenantIsolationValidator(expected_org_id=org_id)

        validator.record_access(org_id, resource_type="document")

        assert validator.get_violations() == []


class TestCurrentTenantContextVar:
    """Tests for current tenant context variable functions."""

    def test_set_and_get_tenant(self):
        """set_current_tenant and get_current_tenant work correctly."""
        org_id = uuid4()

        set_current_tenant(org_id)
        result = get_current_tenant()

        assert result == org_id

        # Cleanup
        clear_current_tenant()

    def test_clear_tenant(self):
        """clear_current_tenant removes the tenant."""
        org_id = uuid4()
        set_current_tenant(org_id)

        clear_current_tenant()
        result = get_current_tenant()

        assert result is None

    def test_require_tenant_success(self):
        """require_tenant returns tenant when set."""
        org_id = uuid4()
        set_current_tenant(org_id)

        result = require_tenant()

        assert result == org_id

        # Cleanup
        clear_current_tenant()

    def test_require_tenant_not_set(self):
        """require_tenant raises when no tenant set."""
        clear_current_tenant()

        with pytest.raises(TenantIsolationError):
            require_tenant()


class TestTenantIsolationError:
    """Tests for TenantIsolationError."""

    def test_error_attributes(self):
        """Error captures all relevant attributes."""
        expected = uuid4()
        actual = uuid4()

        error = TenantIsolationError(
            "Cross-tenant access denied",
            expected_org_id=expected,
            actual_org_id=actual,
            operation="read_document",
        )

        assert error.expected_org_id == expected
        assert error.actual_org_id == actual
        assert error.operation == "read_document"
        assert "Cross-tenant access denied" in str(error)


class TestCrossTenantIsolation:
    """Integration tests for cross-tenant isolation scenarios."""

    def test_concurrent_pipeline_isolation(self):
        """Simulate concurrent pipelines with different tenants."""
        org_1 = uuid4()
        org_2 = uuid4()

        # Validator for org_1
        validator_1 = TenantIsolationValidator(expected_org_id=org_1, strict=False)
        # Validator for org_2
        validator_2 = TenantIsolationValidator(expected_org_id=org_2, strict=False)

        # Simulate org_1 accessing its own resources
        validator_1.record_access(org_1, resource_type="doc", resource_id="1")
        validator_1.record_access(org_1, resource_type="doc", resource_id="2")

        # Simulate org_2 accessing its own resources
        validator_2.record_access(org_2, resource_type="doc", resource_id="3")
        validator_2.record_access(org_2, resource_type="doc", resource_id="4")

        # Both should be isolated
        assert validator_1.is_isolated()
        assert validator_2.is_isolated()

        # Simulate cross-tenant access attempt
        validator_1.record_access(org_2, resource_type="doc", resource_id="3")

        # Now org_1 validator should show violation
        assert not validator_1.is_isolated()
        assert validator_2.is_isolated()  # org_2 still clean

    def test_tenant_context_validation_chain(self):
        """Test validation across multiple resources."""
        org_id = uuid4()
        ctx = TenantContext(org_id=org_id)

        # Access multiple resources from same tenant
        resources = [
            (org_id, "document"),
            (org_id, "memory"),
            (org_id, "profile"),
            (None, "shared_config"),  # Shared resource
        ]

        for resource_org_id, resource_type in resources:
            ctx.validate_access(resource_org_id, operation=f"read_{resource_type}")

        # All should pass without raising
