#!/usr/bin/env python3
"""CLI tooling for contract registry management and schema diffing.

Usage:
  python scripts/contracts.py list --module app/pipelines/summarize.py
  python scripts/contracts.py diff --stage summarize --from v1 --to v2
  python scripts/contracts.py plan-upgrade --stage summarize --from v1 --to v2
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from stageflow.contracts import get_contract_suggestion, registry


def _load_module_from_path(module_path: str | Path):
    path = Path(module_path)
    if not path.exists():
        raise FileNotFoundError(f"Module path not found: {module_path}")

    spec = importlib.util.spec_from_file_location("contracts_module", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec from: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["contracts_module"] = module
    spec.loader.exec_module(module)
    return module


def cmd_list(args) -> int:
    """List registered contracts, optionally filtered to a module."""
    if args.module:
        _load_module_from_path(args.module)

    entries = registry.list(stage=args.stage) if args.stage else registry.list()
    if not entries:
        print("No contracts registered.")
        return 0

    for meta in entries:
        print(f"{meta.stage}@{meta.version} – {meta.description or '(no description)'}")
    return 0


def cmd_diff(args) -> int:
    """Diff two contract versions and emit a compatibility report."""
    if args.module:
        _load_module_from_path(args.module)

    try:
        report = registry.diff(stage=args.stage, from_version=args.from_version, to_version=args.to_version)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = {
            "stage": report.stage,
            "from_version": report.from_version,
            "to_version": report.to_version,
            "is_compatible": report.is_compatible,
            "breaking_changes": report.breaking_changes,
            "warnings": report.warnings,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(report.summary())
        if report.breaking_changes:
            print("\nBreaking changes:")
            for change in report.breaking_changes:
                print(f"  - {change}")
        if report.warnings:
            print("\nWarnings:")
            for warn in report.warnings:
                print(f"  - {warn}")

    return 0 if report.is_compatible else 1


def cmd_plan_upgrade(args) -> int:
    """Generate an upgrade plan with remediation steps."""
    if args.module:
        _load_module_from_path(args.module)

    try:
        report = registry.diff(stage=args.stage, from_version=args.from_version, to_version=args.to_version)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    lines = [
        f"## Upgrade Plan: {args.stage} {args.from_version} → {args.to_version}",
        "",
        f"**Compatibility**: {'✅ Compatible' if report.is_compatible else '❌ Breaking'}",
        "",
    ]

    if report.breaking_changes:
        lines.append("### Breaking Changes")
        for change in report.breaking_changes:
            lines.append(f"- {change}")
        lines.append("")

    if report.warnings:
        lines.append("### Warnings")
        for warn in report.warnings:
            lines.append(f"- {warn}")
        lines.append("")

    # Enrich with suggestion registry if available
    suggestion = get_contract_suggestion("CONTRACT-004-SCHEMA_CHANGE")
    if suggestion and not report.is_compatible:
        lines.append("### Suggested Remediation")
        for step in suggestion.fix_steps:
            lines.append(f"1. {step}")
        lines.append("")
        if suggestion.doc_url:
            lines.append(f"See: {suggestion.doc_url}")

    print("\n".join(lines))
    return 0 if report.is_compatible else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Contract registry management and schema diffing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/contracts.py list --module app/pipelines/summarize.py
  python scripts/contracts.py diff --stage summarize --from v1 --to v2
  python scripts/contracts.py plan-upgrade --stage summarize --from v1 --to v2 --json
        """,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    list_parser = subparsers.add_parser("list", help="List registered contracts")
    list_parser.add_argument("--module", help="Python module path to load contracts from")
    list_parser.add_argument("--stage", help="Filter by stage name")

    # diff
    diff_parser = subparsers.add_parser("diff", help="Diff two contract versions")
    diff_parser.add_argument("--module", help="Python module path to load contracts from")
    diff_parser.add_argument("--stage", required=True, help="Stage name")
    diff_parser.add_argument("--from", required=True, dest="from_version", help="Source version")
    diff_parser.add_argument("--to", required=True, dest="to_version", help="Target version")
    diff_parser.add_argument("--json", action="store_true", help="Emit JSON instead of TTY")

    # plan-upgrade
    plan_parser = subparsers.add_parser("plan-upgrade", help="Generate upgrade plan/runbook")
    plan_parser.add_argument("--module", help="Python module path to load contracts from")
    plan_parser.add_argument("--stage", required=True, help="Stage name")
    plan_parser.add_argument("--from", required=True, dest="from_version", help="Source version")
    plan_parser.add_argument("--to", required=True, dest="to_version", help="Target version")
    plan_parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")

    args = parser.parse_args()
    if args.command == "list":
        return cmd_list(args)
    if args.command == "diff":
        return cmd_diff(args)
    if args.command == "plan-upgrade":
        return cmd_plan_upgrade(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
