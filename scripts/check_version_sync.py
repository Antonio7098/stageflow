#!/usr/bin/env python3
"""Ensure project, documentation, and changelog versions stay aligned."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
CHANGELOG_PATH = REPO_ROOT / "changelog.json"

VERSION_FILES = {
    REPO_ROOT / "README.md": re.compile(r"Latest release:\s*v(?P<version>[^\s]+)"),
    REPO_ROOT
    / "docs/index.md": re.compile(
        r"New in Stageflow (?P<version>[0-9][0-9A-Za-z.\-]*)(?=\*\*|\s|$)"
    ),
}


def load_project_version() -> str:
    with PYPROJECT_PATH.open("rb") as fp:
        data = tomllib.load(fp)
    try:
        return data["project"]["version"]
    except KeyError as exc:  # pragma: no cover - defensive
        raise SystemExit("pyproject.toml is missing [project].version") from exc


def check_version_references(version: str) -> list[str]:
    errors: list[str] = []
    expected = f"v{version}"
    for path, pattern in VERSION_FILES.items():
        content = path.read_text(encoding="utf-8")
        match = pattern.search(content)
        if not match:
            errors.append(f"{path.relative_to(REPO_ROOT)} is missing the latest release marker.")
            continue
        found = match.group("version")
        if found != version:
            errors.append(
                f"{path.relative_to(REPO_ROOT)} references v{found}, expected {expected}."
            )
    return errors


def check_changelog(version: str) -> Iterable[str]:
    expected = f"v{version}"
    with CHANGELOG_PATH.open(encoding="utf-8") as fp:
        data = json.load(fp)
    entries = data.get("entries", [])
    if not entries:
        return [f"{CHANGELOG_PATH.relative_to(REPO_ROOT)} has no entries."]
    latest = entries[0]
    recorded = latest.get("version")
    if recorded != expected:
        return [
            (
                f"{CHANGELOG_PATH.relative_to(REPO_ROOT)} latest entry is {recorded}, "
                f"but pyproject version expects {expected}."
            )
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate that pyproject, docs, and changelog reference the same version."
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress success output (errors will still be printed).",
    )
    args = parser.parse_args(argv)

    version = load_project_version()
    errors = [
        *check_version_references(version),
        *check_changelog(version),
    ]

    if errors:
        for error in errors:
            print(f"[version-sync] {error}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"[version-sync] All references match v{version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
