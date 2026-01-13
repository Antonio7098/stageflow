"""Main entry point for stageflow CLI.

Usage:
    python -m stageflow.cli lint path/to/pipeline.py
    python -m stageflow.cli --help
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="stageflow",
        description="Stageflow command-line tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  lint    Check pipeline dependencies for issues

Examples:
  python -m stageflow.cli lint pipeline.py
  python -m stageflow.cli lint my_app/pipelines/ --verbose
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Lint subcommand
    lint_parser = subparsers.add_parser(
        "lint",
        help="Lint pipeline dependencies",
        description="Check pipeline definitions for dependency issues",
    )
    lint_parser.add_argument(
        "file",
        help="Python file containing pipeline definition(s)",
    )
    lint_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output including info-level issues",
    )
    lint_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    lint_parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "lint":
        from stageflow.cli.lint import lint_pipeline_file, IssueSeverity, DependencyLintResult

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
            has_warnings = any(
                i.severity == IssueSeverity.WARNING for i in result.issues
            )
            if has_warnings:
                result = DependencyLintResult(
                    valid=False,
                    issues=result.issues,
                    stage_count=result.stage_count,
                    dependency_count=result.dependency_count,
                )

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
                filtered_issues = [
                    i for i in result.issues if i.severity != IssueSeverity.INFO
                ]
                result = DependencyLintResult(
                    valid=result.valid,
                    issues=filtered_issues,
                    stage_count=result.stage_count,
                    dependency_count=result.dependency_count,
                )
            print(result)

        return 0 if result.valid else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
