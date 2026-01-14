"""Dependency linting for stageflow pipelines.

This module provides static analysis tools to detect missing or incorrect
dependency declarations in pipeline definitions, helping prevent
UndeclaredDependencyError at runtime.

Usage:
    # Programmatic API
    from stageflow.cli import lint_pipeline
    result = lint_pipeline(pipeline)
    if not result.valid:
        for issue in result.issues:
            print(f"{issue.severity}: {issue.message}")

    # CLI
    python -m stageflow.cli.lint path/to/pipeline.py
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stageflow.pipeline.pipeline import Pipeline


class IssueSeverity(Enum):
    """Severity level for dependency issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class DependencyIssue:
    """A dependency-related issue found during linting.

    Attributes:
        stage_name: The stage where the issue was found.
        message: Human-readable description of the issue.
        severity: How serious the issue is.
        accessed_stage: The stage that was accessed (if applicable).
        suggestion: How to fix the issue (if applicable).
        line_number: Source line number (if available from AST analysis).
    """

    stage_name: str
    message: str
    severity: IssueSeverity
    accessed_stage: str | None = None
    suggestion: str | None = None
    line_number: int | None = None

    def __str__(self) -> str:
        parts = [f"[{self.severity.value.upper()}] {self.stage_name}: {self.message}"]
        if self.suggestion:
            parts.append(f"  Suggestion: {self.suggestion}")
        if self.line_number:
            parts.append(f"  Line: {self.line_number}")
        return "\n".join(parts)


@dataclass
class DependencyLintResult:
    """Result of dependency linting.

    Attributes:
        valid: True if no errors found (warnings are OK).
        issues: List of all issues found.
        stage_count: Number of stages analyzed.
        dependency_count: Total declared dependencies.
    """

    valid: bool
    issues: list[DependencyIssue] = field(default_factory=list)
    stage_count: int = 0
    dependency_count: int = 0

    @property
    def errors(self) -> list[DependencyIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity == IssueSeverity.ERROR]

    @property
    def warnings(self) -> list[DependencyIssue]:
        """Get only warning-level issues."""
        return [i for i in self.issues if i.severity == IssueSeverity.WARNING]

    def __str__(self) -> str:
        if self.valid:
            status = "✓ Pipeline dependencies are valid"
        else:
            status = f"✗ Found {len(self.errors)} error(s)"

        lines = [
            status,
            f"  Stages: {self.stage_count}",
            f"  Dependencies: {self.dependency_count}",
        ]

        if self.issues:
            lines.append("\nIssues:")
            for issue in self.issues:
                lines.append(f"  {issue}")

        return "\n".join(lines)


def lint_pipeline(pipeline: Pipeline) -> DependencyLintResult:
    """Lint a Pipeline for dependency issues.

    Performs static analysis on a Pipeline to detect:
    - Circular dependencies
    - References to non-existent stages
    - Orphaned stages (no dependencies and not depended upon)
    - Self-dependencies

    Args:
        pipeline: The Pipeline instance to lint.

    Returns:
        DependencyLintResult with validation status and issues.

    Example:
        pipeline = Pipeline().with_stage("a", StageA, StageKind.TRANSFORM)
        result = lint_pipeline(pipeline)
        if not result.valid:
            for issue in result.errors:
                print(issue)
    """
    issues: list[DependencyIssue] = []
    stage_names = set(pipeline.stages.keys())
    all_deps: set[str] = set()

    # Track dependencies for orphan detection
    depends_on: dict[str, set[str]] = {}
    depended_by: dict[str, set[str]] = {name: set() for name in stage_names}

    for name, spec in pipeline.stages.items():
        deps = set(spec.dependencies)
        depends_on[name] = deps
        all_deps.update(deps)

        # Check for self-dependency
        if name in deps:
            issues.append(
                DependencyIssue(
                    stage_name=name,
                    message=f"Stage '{name}' depends on itself",
                    severity=IssueSeverity.ERROR,
                    accessed_stage=name,
                    suggestion=f"Remove '{name}' from its own dependencies",
                )
            )

        # Check for non-existent dependencies
        for dep in deps:
            if dep not in stage_names:
                issues.append(
                    DependencyIssue(
                        stage_name=name,
                        message=f"Dependency '{dep}' does not exist in pipeline",
                        severity=IssueSeverity.ERROR,
                        accessed_stage=dep,
                        suggestion=f"Add stage '{dep}' to the pipeline or remove it from dependencies",
                    )
                )
            else:
                depended_by[dep].add(name)

    # Check for circular dependencies using DFS
    def find_cycle(start: str, visited: set[str], path: list[str]) -> list[str] | None:
        if start in visited:
            cycle_start = path.index(start)
            return path[cycle_start:] + [start]

        visited.add(start)
        path.append(start)

        for dep in depends_on.get(start, set()):
            if dep in stage_names:  # Only check existing stages
                result = find_cycle(dep, visited.copy(), path.copy())
                if result:
                    return result

        return None

    for stage_name in stage_names:
        cycle = find_cycle(stage_name, set(), [])
        if cycle and cycle[0] == stage_name:  # Only report once per cycle
            cycle_str = " -> ".join(cycle)
            issues.append(
                DependencyIssue(
                    stage_name=stage_name,
                    message=f"Circular dependency detected: {cycle_str}",
                    severity=IssueSeverity.ERROR,
                    suggestion="Break the cycle by removing one of the dependencies",
                )
            )

    # Check for orphaned stages (warning only)
    for name in stage_names:
        has_deps = bool(depends_on.get(name))
        is_depended = bool(depended_by.get(name))

        if not has_deps and not is_depended and len(stage_names) > 1:
            issues.append(
                DependencyIssue(
                    stage_name=name,
                    message=f"Stage '{name}' is isolated (no dependencies and nothing depends on it)",
                    severity=IssueSeverity.WARNING,
                    suggestion="Consider adding dependencies or removing if unused",
                )
            )

    # Deduplicate issues (especially for cycles)
    seen_messages: set[str] = set()
    unique_issues: list[DependencyIssue] = []
    for issue in issues:
        key = f"{issue.stage_name}:{issue.message}"
        if key not in seen_messages:
            seen_messages.add(key)
            unique_issues.append(issue)

    has_errors = any(i.severity == IssueSeverity.ERROR for i in unique_issues)

    return DependencyLintResult(
        valid=not has_errors,
        issues=unique_issues,
        stage_count=len(stage_names),
        dependency_count=len(all_deps),
    )


def lint_pipeline_file(file_path: str | Path) -> DependencyLintResult:
    """Lint a pipeline definition from a Python file.

    Attempts to find and lint Pipeline instances defined in the file.
    Looks for:
    - Functions that return Pipeline instances
    - Module-level Pipeline variables
    - create_*_pipeline() factory functions

    Args:
        file_path: Path to the Python file containing pipeline definitions.

    Returns:
        DependencyLintResult with validation status and issues.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ImportError: If the file can't be imported.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Pipeline file not found: {file_path}")

    # Load the module
    spec = importlib.util.spec_from_file_location("pipeline_module", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from: {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["pipeline_module"] = module

    try:
        spec.loader.exec_module(module)
    except Exception as e:
        raise ImportError(f"Error executing module {file_path}: {e}") from e

    # Import Pipeline for isinstance checks
    from stageflow.pipeline.pipeline import Pipeline

    # Find Pipeline instances
    pipelines_found: list[tuple[str, Pipeline]] = []

    for name in dir(module):
        if name.startswith("_"):
            continue

        obj = getattr(module, name)

        # Check if it's a Pipeline instance
        if isinstance(obj, Pipeline):
            pipelines_found.append((name, obj))

        # Check if it's a function that returns a Pipeline
        elif callable(obj) and (name.startswith("create_") or name.endswith("_pipeline")):
            try:
                result = obj()
                if isinstance(result, Pipeline):
                    pipelines_found.append((name, result))
            except Exception:
                # Function requires arguments, skip
                pass

    if not pipelines_found:
        return DependencyLintResult(
            valid=True,
            issues=[
                DependencyIssue(
                    stage_name="<module>",
                    message="No Pipeline instances found in file",
                    severity=IssueSeverity.WARNING,
                    suggestion="Define a Pipeline instance or create_*_pipeline() function",
                )
            ],
            stage_count=0,
            dependency_count=0,
        )

    # Lint all found pipelines and combine results
    all_issues: list[DependencyIssue] = []
    total_stages = 0
    total_deps = 0

    for name, pipeline in pipelines_found:
        result = lint_pipeline(pipeline)
        # Prefix issues with pipeline name
        for issue in result.issues:
            prefixed = DependencyIssue(
                stage_name=f"{name}.{issue.stage_name}",
                message=issue.message,
                severity=issue.severity,
                accessed_stage=issue.accessed_stage,
                suggestion=issue.suggestion,
                line_number=issue.line_number,
            )
            all_issues.append(prefixed)
        total_stages += result.stage_count
        total_deps += result.dependency_count

    has_errors = any(i.severity == IssueSeverity.ERROR for i in all_issues)

    return DependencyLintResult(
        valid=not has_errors,
        issues=all_issues,
        stage_count=total_stages,
        dependency_count=total_deps,
    )


class DependencyAccessVisitor(ast.NodeVisitor):
    """AST visitor to find dependency access patterns in stage code.

    Detects calls to:
    - inputs.get_from(stage_name, ...)
    - inputs.require_from(stage_name, ...)
    - inputs.get_output(stage_name)
    - inputs.has_output(stage_name)
    """

    def __init__(self) -> None:
        self.accessed_stages: list[tuple[str, int]] = []  # (stage_name, line_number)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            method_name = node.func.attr
            if (
                method_name in ("get_from", "require_from", "get_output", "has_output")
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                stage_name = node.args[0].value
                if isinstance(stage_name, str):
                    self.accessed_stages.append((stage_name, node.lineno))
        self.generic_visit(node)


def analyze_stage_source(source: str) -> list[tuple[str, int]]:
    """Analyze stage source code for dependency access patterns.

    Args:
        source: Python source code string.

    Returns:
        List of (stage_name, line_number) tuples for accessed stages.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    visitor = DependencyAccessVisitor()
    visitor.visit(tree)
    return visitor.accessed_stages


def main() -> int:
    """CLI entry point for dependency linting."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Lint stageflow pipelines for dependency issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m stageflow.cli.lint pipeline.py
  python -m stageflow.cli.lint my_app/pipelines/chat.py --verbose
        """,
    )
    parser.add_argument(
        "file",
        help="Python file containing pipeline definition(s)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output including info-level issues",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )

    args = parser.parse_args()

    try:
        result = lint_pipeline_file(args.file)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ImportError as e:
        print(f"Error importing file: {e}", file=sys.stderr)
        return 1

    # Handle strict mode
    if args.strict:
        for issue in result.issues:
            if issue.severity == IssueSeverity.WARNING:
                # Upgrade warning to error
                result = DependencyLintResult(
                    valid=False,
                    issues=result.issues,
                    stage_count=result.stage_count,
                    dependency_count=result.dependency_count,
                )
                break

    # Output
    if args.json:
        import json

        output = {
            "valid": result.valid,
            "stage_count": result.stage_count,
            "dependency_count": result.dependency_count,
            "issues": [
                {
                    "stage_name": i.stage_name,
                    "message": i.message,
                    "severity": i.severity.value,
                    "accessed_stage": i.accessed_stage,
                    "suggestion": i.suggestion,
                    "line_number": i.line_number,
                }
                for i in result.issues
                if args.verbose or i.severity != IssueSeverity.INFO
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        # Filter info issues unless verbose
        if not args.verbose:
            filtered_issues = [i for i in result.issues if i.severity != IssueSeverity.INFO]
            result = DependencyLintResult(
                valid=result.valid,
                issues=filtered_issues,
                stage_count=result.stage_count,
                dependency_count=result.dependency_count,
            )
        print(result)

    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
