git add pyproject.toml && GIT_EDITOR=true git rebase --continue#!/usr/bin/env python3
"""Orchestrate a Stageflow release ensuring versions, tags, and docs stay in sync."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import tomllib
REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_version_sync.py"


def run(cmd: list[str], *, dry_run: bool = False) -> subprocess.CompletedProcess[str] | None:
    if dry_run:
        print(f"[dry-run] {' '.join(cmd)}")
        return None
    return subprocess.run(cmd, cwd=REPO_ROOT, check=True, text=True, capture_output=False)


def captured(cmd: list[str]) -> str:
    result = subprocess.run(cmd, cwd=REPO_ROOT, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def ensure_clean_worktree() -> None:
    status = captured(["git", "status", "--porcelain"])
    if status:
        raise SystemExit("Working tree has uncommitted changes. Please commit or stash them first.")


def ensure_tag_absent(tag_name: str) -> None:
    tags = captured(["git", "tag", "--list", tag_name])
    if tags:
        raise SystemExit(f"Tag {tag_name} already exists. Delete it or bump the version.")


def ensure_on_default_branch(expected: str | None) -> None:
    if expected is None:
        return
    branch = captured(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch != expected:
        raise SystemExit(f"Releases must run from {expected}, but current branch is {branch}.")


def load_project_version() -> str:
    with PYPROJECT_PATH.open("rb") as fp:
        data = tomllib.load(fp)
    return data["project"]["version"]


def invoke_version_check(*, dry_run: bool = False) -> None:
    cmd = [sys.executable, str(CHECK_SCRIPT), "--quiet"]
    if dry_run:
        print(f"[dry-run] {' '.join(cmd)}")
        return
    subprocess.run(cmd, cwd=REPO_ROOT, check=True, text=True)


def tag_release(tag_name: str, *, dry_run: bool = False) -> None:
    run(["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"], dry_run=dry_run)


def push_tag(tag_name: str, *, dry_run: bool = False) -> None:
    run(["git", "push", "origin", tag_name], dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release helper for Stageflow.")
    parser.add_argument(
        "--branch",
        default="main",
        help="Require the release to run from this branch (default: main). Use '' to disable.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push the created tag to origin after tagging.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands that would run without executing them.",
    )
    args = parser.parse_args(argv)

    ensure_on_default_branch(args.branch or None)
    ensure_clean_worktree()
    version = load_project_version()
    tag_name = f"v{version}"
    ensure_tag_absent(tag_name)

    invoke_version_check(dry_run=args.dry_run)
    tag_release(tag_name, dry_run=args.dry_run)

    if args.push:
        push_tag(tag_name, dry_run=args.dry_run)
        print(f"Pushed tag {tag_name} to origin.")
    else:
        print(f"Created tag {tag_name}. Run `git push origin {tag_name}` when ready.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
