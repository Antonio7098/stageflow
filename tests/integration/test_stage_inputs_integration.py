"""Integration tests for StageInputs with key validation and error handling."""

from uuid import uuid4

import pytest

from stageflow.context import ContextSnapshot, RunIdentity
from stageflow.core import StageOutput
from stageflow.stages.inputs import UndeclaredDependencyError, create_stage_inputs


def _make_snapshot():
    """Create a minimal ContextSnapshot for testing."""
    return ContextSnapshot(
        run_id=RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        ),
        topology="test",
        execution_mode="test",
    )


class TestStageInputsIntegration:
    """Integration tests for StageInputs with realistic scenarios."""

    def test_pipeline_data_flow_with_validation(self):
        """Test realistic pipeline data flow with key validation."""
        # Simulate pipeline outputs
        prior_outputs = {
            "auth_stage": StageOutput.ok(
                token="abc123",
                user_id="user_456",
                expires_at="2024-01-01T00:00:00Z"
            ),
            "router_stage": StageOutput.ok(
                route="support",
                confidence=0.95,
                reasoning="User mentioned 'help'"
            ),
            "enrich_stage": StageOutput.ok(
                profile={"tier": "premium", "preferences": {"language": "en"}},
                memory={"last_login": "2024-01-01", "sessions": 5}
            ),
        }

        declared_deps = frozenset(["auth_stage", "router_stage", "enrich_stage"])
        inputs = create_stage_inputs(
            snapshot=_make_snapshot(),
            prior_outputs=prior_outputs,
            declared_deps=declared_deps,
            stage_name="process_stage",
            strict=True
        )

        # Valid access patterns
        assert inputs.get_from("auth_stage", "token") == "abc123"
        assert inputs.get_from("router_stage", "route") == "support"
        assert inputs.get_from("enrich_stage", "profile") == {"tier": "premium", "preferences": {"language": "en"}}

        # Search across stages
        assert inputs.get("token") == "abc123"  # Found in auth_stage
        assert inputs.get("route") == "support"  # Found in router_stage
        assert inputs.get("nonexistent", "default") == "default"

        # Required access
        assert inputs.require_from("auth_stage", "user_id") == "user_456"

    def test_strict_dependency_validation(self):
        """Test that strict mode catches undeclared dependencies."""
        prior_outputs = {
            "declared_stage": StageOutput.ok(value="value1"),
            "undeclared_stage": StageOutput.ok(value="value2"),
        }

        inputs = create_stage_inputs(
            snapshot=_make_snapshot(),
            prior_outputs=prior_outputs,
            declared_deps=frozenset(["declared_stage"]),
            stage_name="test_stage",
            strict=True
        )

        # Can access declared dependency
        assert inputs.get_from("declared_stage", "value") == "value1"

        # Cannot access undeclared dependency
        with pytest.raises(UndeclaredDependencyError) as exc_info:
            inputs.get_from("undeclared_stage", "data")

        assert exc_info.value.stage_name == "undeclared_stage"
        assert exc_info.value.accessing_stage == "test_stage"
        assert "declared_stage" in exc_info.value.declared_deps

    def test_non_strict_mode_access(self):
        """Test that non-strict mode allows accessing any stage."""
        prior_outputs = {
            "stage_a": StageOutput.ok(value="value_a"),
            "stage_b": StageOutput.ok(value="value_b"),
        }

        inputs = create_stage_inputs(
            snapshot=_make_snapshot(),
            prior_outputs=prior_outputs,
            declared_deps=frozenset(["stage_a"]),  # Only declare stage_a
            stage_name="test_stage",
            strict=False  # Non-strict mode
        )

        # Can access both stages in non-strict mode
        assert inputs.get_from("stage_a", "value") == "value_a"
        assert inputs.get_from("stage_b", "value") == "value_b"

    def test_key_validation_in_realistic_scenarios(self):
        """Test key validation with realistic error scenarios."""
        prior_outputs = {
            "llm_stage": StageOutput.ok(
                response="Hello!",
                model="gpt-4",
                usage={"prompt_tokens": 10, "completion_tokens": 5}
            ),
        }

        inputs = create_stage_inputs(
            snapshot=_make_snapshot(),
            prior_outputs=prior_outputs,
            stage_name="test_stage"
        )

        # These common programming errors now raise clear exceptions:

        # 1. None key (common when refactoring)
        with pytest.raises(TypeError, match="StageInputs key must be provided"):
            inputs.get(None)

        # 2. Empty string key (common when using variables that are unset)
        with pytest.raises(ValueError, match="StageInputs key cannot be empty"):
            inputs.get("")

        # 3. Non-string key (common when passing wrong variable type)
        with pytest.raises(TypeError, match="StageInputs key must be a string"):
            inputs.get(123)

        # 4. get_from with None key
        with pytest.raises(TypeError, match="StageInputs key must be provided"):
            inputs.get_from("llm_stage", None)

        # 5. require_from with invalid key
        with pytest.raises(TypeError, match="StageInputs key must be provided"):
            inputs.require_from("llm_stage", None)

    def test_error_messages_are_helpful_for_debugging(self):
        """Test that error messages provide helpful debugging information."""
        prior_outputs = {
            "auth_stage": StageOutput.ok(token="abc123"),
        }

        inputs = create_stage_inputs(
            snapshot=_make_snapshot(),
            prior_outputs=prior_outputs,
            declared_deps=frozenset(["auth_stage"]),
            stage_name="process_stage",
            strict=True
        )

        # Undeclared dependency error should include context
        try:
            inputs.get_from("missing_stage", "key")
        except UndeclaredDependencyError as e:
            assert "process_stage" in str(e)
            assert "missing_stage" in str(e)
            assert "auth_stage" in str(e)

        # Key validation errors should be clear
        try:
            inputs.get_from("auth_stage", "")
        except ValueError as e:
            assert "cannot be empty" in str(e).lower()

        try:
            inputs.get_from("auth_stage", None)
        except TypeError as e:
            assert "must be provided" in str(e).lower()

    def test_complex_pipeline_scenario(self):
        """Test StageInputs in a complex multi-stage scenario."""
        # Simulate outputs from multiple pipeline stages
        prior_outputs = {
            "input_validation": StageOutput.ok(
                valid=True,
                errors=[],
                sanitized_input="Hello world"
            ),
            "auth_check": StageOutput.ok(
                authenticated=True,
                user_id="user_123",
                permissions=["read", "write"]
            ),
            "content_filter": StageOutput.ok(
                allowed=True,
                blocked_phrases=[],
                confidence=0.98
            ),
            "llm_process": StageOutput.ok(
                response="Hi there! How can I help you?",
                model="gpt-4",
                usage={"prompt_tokens": 15, "completion_tokens": 8},
                latency_ms=245
            ),
            "output_format": StageOutput.ok(
                formatted_response="Hi there! How can I help you?",
                metadata={"format": "text", "length": 31}
            ),
        }

        declared_deps = frozenset(prior_outputs.keys())
        inputs = create_stage_inputs(
            snapshot=_make_snapshot(),
            prior_outputs=prior_outputs,
            declared_deps=declared_deps,
            stage_name="final_stage",
            strict=True
        )

        # Test accessing data from the pipeline
        assert inputs.get_from("input_validation", "valid") is True
        assert inputs.get_from("auth_check", "authenticated") is True
        assert inputs.get_from("content_filter", "allowed") is True
        assert inputs.get_from("llm_process", "response") == "Hi there! How can I help you?"
        assert inputs.get_from("output_format", "formatted_response") == "Hi there! How can I help you?"

        # Test searching for common keys
        assert inputs.get("response") == "Hi there! How can I help you?"
        assert inputs.get("user_id") == "user_123"
        assert inputs.get("model") == "gpt-4"

        # Test required access for critical data
        user_id = inputs.require_from("auth_check", "user_id")
        assert user_id == "user_123"

        # Test accessing complete outputs
        llm_output = inputs.get_output("llm_process")
        assert llm_output is not None
        assert llm_output.data["latency_ms"] == 245

    def test_backward_compatibility_with_existing_code(self):
        """Test that existing valid code continues to work."""
        prior_outputs = {
            "stage1": StageOutput.ok(key1="value1", key2="value2"),
            "stage2": StageOutput.ok(nested={"data": "value"}),
        }

        inputs = create_stage_inputs(
            snapshot=_make_snapshot(),
            prior_outputs=prior_outputs,
            stage_name="test_stage"
        )

        # All these valid patterns should continue to work:
        assert inputs.get("key1") == "value1"
        assert inputs.get("key1", "default") == "value1"
        assert inputs.get("missing", "default") == "default"

        assert inputs.get_from("stage1", "key1") == "value1"
        assert inputs.get_from("stage1", "key2") == "value2"
        assert inputs.get_from("stage1", "missing", "default") == "default"

        assert inputs.has_output("stage1") is True
        assert inputs.has_output("missing") is False

        output = inputs.get_output("stage1")
        assert output is not None
        assert output.data["key1"] == "value1"
