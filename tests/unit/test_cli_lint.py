"""Tests for the dependency lint CLI module."""

from __future__ import annotations

import pytest

from stageflow import Pipeline, StageKind, StageOutput, StageContext
from stageflow.cli.lint import (
    DependencyIssue,
    DependencyLintResult,
    IssueSeverity,
    lint_pipeline,
    analyze_stage_source,
)


class MockStage:
    """Mock stage for testing."""

    name = "mock"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        return StageOutput.ok()


class TestLintPipeline:
    """Tests for lint_pipeline function."""

    def test_valid_pipeline_passes(self):
        """Valid pipeline with correct dependencies should pass."""
        pipeline = (
            Pipeline()
            .with_stage("a", MockStage, StageKind.TRANSFORM)
            .with_stage("b", MockStage, StageKind.TRANSFORM, dependencies=("a",))
            .with_stage("c", MockStage, StageKind.TRANSFORM, dependencies=("b",))
        )

        result = lint_pipeline(pipeline)

        assert result.valid is True
        assert len(result.errors) == 0
        assert result.stage_count == 3
        assert result.dependency_count == 2

    def test_detects_self_dependency(self):
        """Should detect stage depending on itself."""
        pipeline = (
            Pipeline()
            .with_stage("a", MockStage, StageKind.TRANSFORM, dependencies=("a",))
        )

        result = lint_pipeline(pipeline)

        assert result.valid is False
        # Self-dependency is detected both as self-reference and as a cycle
        assert len(result.errors) >= 1
        assert any("depends on itself" in e.message for e in result.errors)

    def test_detects_nonexistent_dependency(self):
        """Should detect dependency on non-existent stage."""
        pipeline = (
            Pipeline()
            .with_stage("a", MockStage, StageKind.TRANSFORM, dependencies=("nonexistent",))
        )

        result = lint_pipeline(pipeline)

        assert result.valid is False
        assert len(result.errors) == 1
        assert "does not exist" in result.errors[0].message
        assert result.errors[0].accessed_stage == "nonexistent"

    def test_detects_circular_dependency(self):
        """Should detect circular dependencies."""
        pipeline = (
            Pipeline()
            .with_stage("a", MockStage, StageKind.TRANSFORM, dependencies=("c",))
            .with_stage("b", MockStage, StageKind.TRANSFORM, dependencies=("a",))
            .with_stage("c", MockStage, StageKind.TRANSFORM, dependencies=("b",))
        )

        result = lint_pipeline(pipeline)

        assert result.valid is False
        assert any("Circular dependency" in e.message for e in result.errors)

    def test_detects_orphaned_stage(self):
        """Should warn about isolated stages."""
        pipeline = (
            Pipeline()
            .with_stage("a", MockStage, StageKind.TRANSFORM)
            .with_stage("b", MockStage, StageKind.TRANSFORM, dependencies=("a",))
            .with_stage("orphan", MockStage, StageKind.TRANSFORM)  # No deps, not depended on
        )

        result = lint_pipeline(pipeline)

        # Should be valid but have warning
        assert result.valid is True
        assert len(result.warnings) == 1
        assert "isolated" in result.warnings[0].message

    def test_single_stage_not_orphaned(self):
        """Single stage pipeline should not warn about orphan."""
        pipeline = Pipeline().with_stage("only", MockStage, StageKind.TRANSFORM)

        result = lint_pipeline(pipeline)

        assert result.valid is True
        assert len(result.warnings) == 0


class TestDependencyIssue:
    """Tests for DependencyIssue dataclass."""

    def test_str_format(self):
        """String representation should include key info."""
        issue = DependencyIssue(
            stage_name="my_stage",
            message="Test message",
            severity=IssueSeverity.ERROR,
            suggestion="Fix it",
        )

        str_repr = str(issue)

        assert "[ERROR]" in str_repr
        assert "my_stage" in str_repr
        assert "Test message" in str_repr
        assert "Fix it" in str_repr

    def test_with_line_number(self):
        """Should include line number when available."""
        issue = DependencyIssue(
            stage_name="stage",
            message="Error",
            severity=IssueSeverity.ERROR,
            line_number=42,
        )

        assert "42" in str(issue)


class TestDependencyLintResult:
    """Tests for DependencyLintResult dataclass."""

    def test_errors_property(self):
        """errors property should filter to ERROR severity."""
        result = DependencyLintResult(
            valid=False,
            issues=[
                DependencyIssue("a", "error", IssueSeverity.ERROR),
                DependencyIssue("b", "warning", IssueSeverity.WARNING),
                DependencyIssue("c", "error2", IssueSeverity.ERROR),
            ],
        )

        assert len(result.errors) == 2
        assert all(e.severity == IssueSeverity.ERROR for e in result.errors)

    def test_warnings_property(self):
        """warnings property should filter to WARNING severity."""
        result = DependencyLintResult(
            valid=True,
            issues=[
                DependencyIssue("a", "error", IssueSeverity.ERROR),
                DependencyIssue("b", "warning", IssueSeverity.WARNING),
            ],
        )

        assert len(result.warnings) == 1
        assert result.warnings[0].severity == IssueSeverity.WARNING

    def test_str_valid_pipeline(self):
        """String for valid pipeline should show success."""
        result = DependencyLintResult(valid=True, stage_count=3, dependency_count=2)

        str_repr = str(result)

        assert "valid" in str_repr.lower() or "✓" in str_repr
        assert "3" in str_repr

    def test_str_invalid_pipeline(self):
        """String for invalid pipeline should show errors."""
        result = DependencyLintResult(
            valid=False,
            issues=[DependencyIssue("a", "error", IssueSeverity.ERROR)],
        )

        str_repr = str(result)

        assert "error" in str_repr.lower() or "✗" in str_repr


class TestAnalyzeStageSource:
    """Tests for source code analysis."""

    def test_detects_get_from_calls(self):
        """Should detect inputs.get_from() calls."""
        source = '''
async def execute(self, ctx):
    value = ctx.inputs.get_from("upstream", "key")
    return value
'''

        accessed = analyze_stage_source(source)

        assert len(accessed) == 1
        assert accessed[0][0] == "upstream"

    def test_detects_require_from_calls(self):
        """Should detect inputs.require_from() calls."""
        source = '''
async def execute(self, ctx):
    value = ctx.inputs.require_from("required_stage", "data")
    return value
'''

        accessed = analyze_stage_source(source)

        assert len(accessed) == 1
        assert accessed[0][0] == "required_stage"

    def test_detects_multiple_accesses(self):
        """Should detect multiple dependency accesses."""
        source = '''
async def execute(self, ctx):
    a = ctx.inputs.get_from("stage_a", "value")
    b = ctx.inputs.get_from("stage_b", "value")
    c = ctx.inputs.require_from("stage_c", "value")
    return a + b + c
'''

        accessed = analyze_stage_source(source)

        stage_names = [a[0] for a in accessed]
        assert "stage_a" in stage_names
        assert "stage_b" in stage_names
        assert "stage_c" in stage_names

    def test_handles_invalid_syntax(self):
        """Should return empty list for invalid Python."""
        source = "this is not valid python {{{{"

        accessed = analyze_stage_source(source)

        assert accessed == []
