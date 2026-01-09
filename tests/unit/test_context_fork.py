"""Unit tests for PipelineContext.fork() and subpipeline support."""

from __future__ import annotations

from uuid import uuid4

import pytest

from stageflow import PipelineContext


class TestPipelineContextFork:
    """Tests for PipelineContext.fork() method."""

    @pytest.fixture
    def parent_context(self) -> PipelineContext:
        """Create a parent context for forking tests."""
        return PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="parent_pipeline",
            execution_mode="practice",
            service="test",
            data={"parent_key": "parent_value", "shared": "data"},
        )

    def test_fork_creates_new_context(self, parent_context: PipelineContext) -> None:
        """Fork creates a new PipelineContext instance."""
        child_run_id = uuid4()
        correlation_id = uuid4()

        child = parent_context.fork(
            child_run_id=child_run_id,
            parent_stage_id="tool_executor",
            correlation_id=correlation_id,
        )

        assert child is not parent_context
        assert child.pipeline_run_id == child_run_id

    def test_fork_sets_parent_references(self, parent_context: PipelineContext) -> None:
        """Fork sets parent_run_id and parent_stage_id."""
        child_run_id = uuid4()
        correlation_id = uuid4()

        child = parent_context.fork(
            child_run_id=child_run_id,
            parent_stage_id="my_stage",
            correlation_id=correlation_id,
        )

        assert child.parent_run_id == parent_context.pipeline_run_id
        assert child.parent_stage_id == "my_stage"
        assert child.correlation_id == correlation_id

    def test_fork_inherits_auth_context(self, parent_context: PipelineContext) -> None:
        """Fork inherits user_id, org_id, session_id."""
        child = parent_context.fork(
            child_run_id=uuid4(),
            parent_stage_id="stage",
            correlation_id=uuid4(),
        )

        assert child.user_id == parent_context.user_id
        assert child.org_id == parent_context.org_id
        assert child.session_id == parent_context.session_id
        assert child.request_id == parent_context.request_id

    def test_fork_inherits_topology_by_default(self, parent_context: PipelineContext) -> None:
        """Fork inherits topology and execution_mode by default."""
        child = parent_context.fork(
            child_run_id=uuid4(),
            parent_stage_id="stage",
            correlation_id=uuid4(),
        )

        assert child.topology == parent_context.topology
        assert child.execution_mode == parent_context.execution_mode

    def test_fork_can_override_topology(self, parent_context: PipelineContext) -> None:
        """Fork can specify different topology and execution_mode."""
        child = parent_context.fork(
            child_run_id=uuid4(),
            parent_stage_id="stage",
            correlation_id=uuid4(),
            topology="child_pipeline",
            execution_mode="assessment",
        )

        assert child.topology == "child_pipeline"
        assert child.execution_mode == "assessment"

    def test_fork_has_fresh_data_dict(self, parent_context: PipelineContext) -> None:
        """Fork has empty data dict (not shared with parent)."""
        child = parent_context.fork(
            child_run_id=uuid4(),
            parent_stage_id="stage",
            correlation_id=uuid4(),
        )

        assert child.data == {}
        assert child.data is not parent_context.data

    def test_fork_has_fresh_artifacts_list(self, parent_context: PipelineContext) -> None:
        """Fork has empty artifacts list."""
        parent_context.artifacts.append({"type": "test"})

        child = parent_context.fork(
            child_run_id=uuid4(),
            parent_stage_id="stage",
            correlation_id=uuid4(),
        )

        assert child.artifacts == []
        assert child.artifacts is not parent_context.artifacts

    def test_fork_provides_readonly_parent_data(self, parent_context: PipelineContext) -> None:
        """Fork can read parent data via get_parent_data()."""
        child = parent_context.fork(
            child_run_id=uuid4(),
            parent_stage_id="stage",
            correlation_id=uuid4(),
        )

        assert child.get_parent_data("parent_key") == "parent_value"
        assert child.get_parent_data("shared") == "data"
        assert child.get_parent_data("nonexistent") is None
        assert child.get_parent_data("nonexistent", "default") == "default"

    def test_fork_is_child_run_property(self, parent_context: PipelineContext) -> None:
        """is_child_run returns True for forked context."""
        assert parent_context.is_child_run is False

        child = parent_context.fork(
            child_run_id=uuid4(),
            parent_stage_id="stage",
            correlation_id=uuid4(),
        )

        assert child.is_child_run is True

    def test_fork_not_canceled_by_default(self, parent_context: PipelineContext) -> None:
        """Forked context starts not canceled."""
        parent_context.mark_canceled()

        child = parent_context.fork(
            child_run_id=uuid4(),
            parent_stage_id="stage",
            correlation_id=uuid4(),
        )

        assert child.canceled is False
        assert child.is_canceled is False


class TestPipelineContextCancellation:
    """Tests for context cancellation."""

    def test_mark_canceled(self) -> None:
        """mark_canceled() sets canceled flag."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=None,
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
        )

        assert ctx.is_canceled is False
        ctx.mark_canceled()
        assert ctx.is_canceled is True
        assert ctx.canceled is True


class TestPipelineContextToDict:
    """Tests for context serialization."""

    def test_to_dict_includes_parent_fields(self) -> None:
        """to_dict() includes parent correlation fields for child contexts."""
        parent_run_id = uuid4()
        correlation_id = uuid4()

        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=None,
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
            parent_run_id=parent_run_id,
            parent_stage_id="spawner_stage",
            correlation_id=correlation_id,
        )

        result = ctx.to_dict()

        assert result["parent_run_id"] == str(parent_run_id)
        assert result["parent_stage_id"] == "spawner_stage"
        assert result["correlation_id"] == str(correlation_id)

    def test_to_dict_omits_parent_fields_for_root(self) -> None:
        """to_dict() omits parent fields for root contexts."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=None,
            session_id=None,
            user_id=None,
            org_id=None,
            interaction_id=None,
        )

        result = ctx.to_dict()

        assert "parent_run_id" not in result
        assert "parent_stage_id" not in result
        assert "correlation_id" not in result
