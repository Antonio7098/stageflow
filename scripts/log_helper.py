#!/usr/bin/env python3
"""Helper CLI to manage changelog.json and bugs.json without manual JSON editing."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG_PATH = REPO_ROOT / "changelog.json"
BUGS_PATH = REPO_ROOT / "bugs.json"


def prompt(message: str, *, default: str | None = None, required: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{message}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""
        print("Value required, please try again.")


def prompt_yes_no(message: str, *, default: str = "y") -> bool:
    mapping = {"y": True, "yes": True, "n": False, "no": False}
    suffix = " [Y/n]" if default.lower() in {"y", "yes"} else " [y/N]"
    while True:
        value = input(f"{message}{suffix}: ").strip().lower()
        if not value:
            value = default.lower()
        if value in mapping:
            return mapping[value]
        print("Please answer y or n.")


def ensure_json(
    path: Path, root_key: str, template: dict[str, Any] | None = None
) -> dict[str, Any]:
    if not path.exists():
        data: dict[str, Any] = template.copy() if template else {}
        data.setdefault(root_key, [])
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return data

    with path.open(encoding="utf-8") as fp:
        data = json.load(fp)

    if template:
        for key, value in template.items():
            data.setdefault(key, value)

    data.setdefault(root_key, [])
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def parse_csv_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def collect_changelog_changes(
    existing: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if existing and prompt_yes_no("Reuse existing change list?", default="y"):
        return existing

    changes: list[dict[str, Any]] = []
    while True:
        change_type = prompt(
            "Change type (added/changed/fixed/removed)",
            default="changed",
            required=True,
        )
        area = prompt("Area (subsystem/feature)", required=True)
        description = prompt("Description", required=True)
        commit = prompt("Commit hash/link", default="pending", required=True)
        files = parse_csv_list(
            prompt("Files affected (comma separated)", required=True)
        )
        issues = parse_csv_list(
            prompt("Issues (comma separated, optional)", default="")
        )

        changes.append(
            {
                "type": change_type,
                "area": area,
                "description": description,
                "commit": commit,
                "files_affected": files,
                "issues": issues,
            }
        )

        more = prompt("Add another change? (y/N)", default="n").lower()
        if more not in {"y", "yes"}:
            break

    if not changes:
        raise SystemExit("At least one change entry is required.")
    return changes


def add_changelog_entry(file_path: Path) -> None:
    today = datetime.now(UTC).date().isoformat()
    data = ensure_json(
        file_path,
        "entries",
        template={
            "template": {
                "version": "vYYYY.MM.DD or semantic version",
                "date": "ISO-8601 release date",
                "changes": [
                    {
                        "type": "added | changed | fixed | removed",
                        "area": "subsystem or feature name",
                        "description": "Concise summary of the change",
                        "commit": "git hash or link",
                        "files_affected": ["List of key files or directories impacted"],
                        "issues": ["Optional list of bug IDs or tickets"],
                    }
                ],
            }
        },
    )

    version = prompt("Version (e.g. v0.1.2)", required=True)
    date = prompt("Date (ISO-8601)", default=today, required=True)
    changes = collect_changelog_changes()

    entry = {"version": version, "date": date, "changes": changes}

    data["entries"].insert(0, entry)
    write_json(file_path, data)
    print(f"Added changelog entry for {version} to {file_path}")


def select_entry(
    entries: list[dict[str, Any]],
    *,
    key_field: str,
    key_value: str | None,
    label_builder: Callable[[dict[str, Any]], str],
) -> tuple[int, dict[str, Any]]:
    if not entries:
        raise SystemExit("No entries available.")

    if key_value:
        for idx, entry in enumerate(entries):
            if entry.get(key_field) == key_value:
                return idx, entry
        raise SystemExit(f"No entry found with {key_field}={key_value}.")

    print("Available entries:")
    for idx, entry in enumerate(entries[:20]):
        print(f"  {idx}: {label_builder(entry)}")

    while True:
        choice = prompt("Select entry index", required=True)
        if choice.isdigit():
            idx = int(choice)
            if 0 <= idx < len(entries):
                return idx, entries[idx]
        print("Invalid selection, try again.")


def edit_changelog_entry(file_path: Path, *, version: str | None = None) -> None:
    today = datetime.now(UTC).date().isoformat()
    data = ensure_json(file_path, "entries")
    entries = data["entries"]
    idx, entry = select_entry(
        entries,
        key_field="version",
        key_value=version,
        label_builder=lambda e: f"{e.get('version')} ({e.get('date')})",
    )

    new_version = prompt("Version", default=entry.get("version", ""), required=True)
    new_date = prompt(
        "Date (ISO-8601)", default=entry.get("date", today), required=True
    )
    changes = collect_changelog_changes(entry.get("changes"))

    entries[idx] = {"version": new_version, "date": new_date, "changes": changes}
    write_json(file_path, data)
    print(f"Updated changelog entry for {new_version} in {file_path}")


def delete_changelog_entry(file_path: Path, *, version: str | None = None) -> None:
    data = ensure_json(file_path, "entries")
    entries = data["entries"]
    idx, entry = select_entry(
        entries,
        key_field="version",
        key_value=version,
        label_builder=lambda e: f"{e.get('version')} ({e.get('date')})",
    )

    if not prompt_yes_no(
        f"Delete changelog entry {entry.get('version')}?", default="n"
    ):
        print("Aborted.")
        return

    removed = entries.pop(idx)
    write_json(file_path, data)
    print(f"Deleted changelog entry {removed.get('version')} from {file_path}")


def add_bug_entry(file_path: Path) -> None:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    data = ensure_json(
        file_path,
        "bugs",
        template={
            "template": {
                "id": "BUG-YYYYMMDD-XX",
                "title": "Short summary of the defect",
                "status": "open | in_progress | closed",
                "severity": "low | medium | high | critical",
                "area": "subsystem or feature name",
                "introduced_in": "commit hash or version where the bug first appeared",
                "fixed_in": "commit hash or version containing the fix",
                "reported_by": "person or automation that caught the bug",
                "owner": "engineer responsible for the fix",
                "created_at": "ISO-8601 timestamp when the bug was logged",
                "resolved_at": "ISO-8601 timestamp when the bug was closed (null if open)",
                "description": "Detailed description, reproduction steps, and observed behavior",
                "resolution": "Summary of the fix or mitigation",
                "links": ["Optional URLs to PRs, tickets, dashboards"],
            }
        },
    )

    bug = {
        "id": prompt("Bug ID (e.g. BUG-20260115-01)", required=True),
        "title": prompt("Title", required=True),
        "status": prompt("Status", default="open", required=True),
        "severity": prompt("Severity", default="medium", required=True),
        "area": prompt("Area", required=True),
        "introduced_in": prompt("Introduced in (commit/version)", default="unknown"),
        "fixed_in": prompt("Fixed in (commit/version)", default="pending"),
        "reported_by": prompt("Reported by", default="unknown"),
        "owner": prompt("Owner", default="unassigned"),
        "created_at": prompt("Created at (ISO-8601)", default=now, required=True),
        "resolved_at": prompt("Resolved at (ISO-8601, blank if open)", default=""),
        "description": prompt("Description", required=True),
        "resolution": prompt("Resolution", default=""),
        "links": parse_csv_list(prompt("Links (comma separated)", default="")),
    }

    if not bug["resolved_at"]:
        bug["resolved_at"] = None

    data["bugs"].insert(0, bug)
    write_json(file_path, data)
    print(f"Recorded bug {bug['id']} in {file_path}")


def edit_bug_entry(file_path: Path, *, bug_id: str | None = None) -> None:
    data = ensure_json(file_path, "bugs")
    bugs = data["bugs"]
    idx, bug = select_entry(
        bugs,
        key_field="id",
        key_value=bug_id,
        label_builder=lambda b: f"{b.get('id')} ({b.get('status')})",
    )

    def field(name: str, default: str | None = None, required: bool = False) -> str:
        current = bug.get(name)
        current_str = "" if current is None else str(current)
        return prompt(
            name.replace("_", " ").title(),
            default=current_str or default,
            required=required,
        )

    updated = {
        "id": field("id", required=True),
        "title": field("title", required=True),
        "status": field("status", default="open", required=True),
        "severity": field("severity", default="medium", required=True),
        "area": field("area", required=True),
        "introduced_in": field("introduced_in", default="unknown"),
        "fixed_in": field("fixed_in", default="pending"),
        "reported_by": field("reported_by", default="unknown"),
        "owner": field("owner", default="unassigned"),
        "created_at": field(
            "created_at",
            default=bug.get("created_at") or datetime.now(UTC).isoformat(),
        ),
        "resolved_at": field("resolved_at", default=""),
        "description": field("description", required=True),
        "resolution": field("resolution", default=""),
        "links": parse_csv_list(field("links", default=",".join(bug.get("links", [])))),
    }

    if not updated["resolved_at"]:
        updated["resolved_at"] = None

    bugs[idx] = updated
    write_json(file_path, data)
    print(f"Updated bug {updated['id']} in {file_path}")


def delete_bug_entry(file_path: Path, *, bug_id: str | None = None) -> None:
    data = ensure_json(file_path, "bugs")
    bugs = data["bugs"]
    idx, bug = select_entry(
        bugs,
        key_field="id",
        key_value=bug_id,
        label_builder=lambda b: f"{b.get('id')} ({b.get('status')})",
    )

    if not prompt_yes_no(f"Delete bug {bug.get('id')}?", default="n"):
        print("Aborted.")
        return

    removed = bugs.pop(idx)
    write_json(file_path, data)
    print(f"Deleted bug {removed.get('id')} from {file_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage changelog.json and bugs.json entries"
    )
    subparsers = parser.add_subparsers(dest="target", required=True)

    changelog_parser = subparsers.add_parser(
        "changelog", help="Manage changelog entries"
    )
    changelog_parser.add_argument(
        "--file",
        type=Path,
        default=CHANGELOG_PATH,
        help="Path to changelog JSON (default: repo changelog.json)",
    )
    changelog_sub = changelog_parser.add_subparsers(dest="action", required=True)
    changelog_sub.add_parser("add", help="Add a changelog entry")
    edit_parser = changelog_sub.add_parser("edit", help="Edit an existing entry")
    edit_parser.add_argument("--version", help="Version to edit")
    delete_parser = changelog_sub.add_parser("delete", help="Delete an entry")
    delete_parser.add_argument("--version", help="Version to delete")

    bugs_parser = subparsers.add_parser("bugs", help="Manage bug entries")
    bugs_parser.add_argument(
        "--file",
        type=Path,
        default=BUGS_PATH,
        help="Path to bugs JSON (default: repo bugs.json)",
    )
    bugs_sub = bugs_parser.add_subparsers(dest="action", required=True)
    bugs_sub.add_parser("add", help="Add a bug entry")
    bugs_edit = bugs_sub.add_parser("edit", help="Edit a bug entry")
    bugs_edit.add_argument("--id", help="Bug ID to edit")
    bugs_delete = bugs_sub.add_parser("delete", help="Delete a bug entry")
    bugs_delete.add_argument("--id", help="Bug ID to delete")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.target == "changelog":
        if args.action == "add":
            add_changelog_entry(args.file)
        elif args.action == "edit":
            edit_changelog_entry(args.file, version=args.version)
        elif args.action == "delete":
            delete_changelog_entry(args.file, version=args.version)
        else:  # pragma: no cover
            parser.error("Unknown changelog action")
    elif args.target == "bugs":
        if args.action == "add":
            add_bug_entry(args.file)
        elif args.action == "edit":
            edit_bug_entry(args.file, bug_id=args.id)
        elif args.action == "delete":
            delete_bug_entry(args.file, bug_id=args.id)
        else:  # pragma: no cover
            parser.error("Unknown bugs action")
    else:  # pragma: no cover
        parser.error("Unknown target")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
