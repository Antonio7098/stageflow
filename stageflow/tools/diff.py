"""Diff utilities for comparing text, JSON, and structured data.

This module provides diff generation capabilities for agent actions that modify
content. Diffs are essential for:
- Showing what changed in an edit
- Supporting undo operations
- Generating human-readable change summaries
- Recording audit trails
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher, unified_diff
from enum import Enum
from typing import Any


class DiffType(Enum):
    """Type of diff format."""

    UNIFIED = "unified"  # Unified diff format (default)
    CONTEXT = "context"  # Context diff format
    JSON_PATCH = "json_patch"  # JSON Patch format (RFC 6902)
    LINE_BY_LINE = "line_by_line"  # Simple line-by-line comparison


@dataclass(frozen=True, slots=True)
class DiffLine:
    """A single line in a diff."""

    type: str  # "equal", "add", "remove"
    content: str
    line_number_old: int | None = None
    line_number_new: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type,
            "content": self.content,
            "line_number_old": self.line_number_old,
            "line_number_new": self.line_number_new,
        }


@dataclass(frozen=True, slots=True)
class DiffResult:
    """Result of a diff operation.

    Attributes:
        diff_type: The type of diff generated
        old_content: Original content (if kept in memory)
        new_content: New content (if kept in memory)
        diff_output: The diff output string (for unified/context formats)
        changes: List of individual line changes
        additions: Count of added lines
        deletions: Count of deleted lines
        unchanged: Count of unchanged lines
        similarity: Similarity ratio (0.0 to 1.0)
    """

    diff_type: DiffType
    diff_output: str
    changes: list[DiffLine] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    unchanged: int = 0
    similarity: float = 1.0
    old_content: str | None = None
    new_content: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "diff_type": self.diff_type.value,
            "diff_output": self.diff_output,
            "changes": [c.to_dict() for c in self.changes],
            "additions": self.additions,
            "deletions": self.deletions,
            "unchanged": self.unchanged,
            "similarity": self.similarity,
        }

    @property
    def has_changes(self) -> bool:
        """Return True if there are any changes."""
        return self.additions > 0 or self.deletions > 0

    @property
    def change_summary(self) -> str:
        """Get a human-readable summary of changes."""
        parts = []
        if self.additions > 0:
            parts.append(f"+{self.additions}")
        if self.deletions > 0:
            parts.append(f"-{self.deletions}")
        if not parts:
            return "no changes"
        return " ".join(parts)


def diff_text(
    old: str,
    new: str,
    diff_type: DiffType = DiffType.UNIFIED,
    context_lines: int = 3,
    fromfile: str = "a/original",
    tofile: str = "b/modified",
) -> DiffResult:
    """Generate a diff between two text strings.

    Args:
        old: Original text content
        new: New text content
        diff_type: Type of diff to generate
        context_lines: Number of context lines around changes
        fromfile: File name for old content in diff header
        tofile: File name for new content in diff header

    Returns:
        DiffResult with the diff output and statistics

    Example:
        ```python
        old = "Hello\\nWorld"
        new = "Hello\\nPython\\nWorld"
        result = diff_text(old, new)
        print(result.diff_output)
        # --- a/original
        # +++ b/modified
        # @@ -1,2 +1,3 @@
        #  Hello
        # +Python
        #  World
        ```
    """
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    if diff_type == DiffType.UNIFIED:
        diff_lines = list(
            unified_diff(
                old_lines,
                new_lines,
                fromfile=fromfile,
                tofile=tofile,
                n=context_lines,
            )
        )
        diff_output = "".join(diff_lines)
    elif diff_type == DiffType.CONTEXT:
        diff_lines = list(
            unified_diff(
                old_lines,
                new_lines,
                fromfile=fromfile,
                tofile=tofile,
                n=context_lines,
            )
        )
        # Convert to context format by modifying headers
        diff_output = "".join(diff_lines).replace("@@", "****")
    else:
        # For other types, use unified as base
        diff_lines = list(
            unified_diff(
                old_lines,
                new_lines,
                fromfile=fromfile,
                tofile=tofile,
                n=context_lines,
            )
        )
        diff_output = "".join(diff_lines)

    # Parse changes for statistics
    changes = _parse_diff_changes(old_lines, new_lines, diff_lines)

    # Calculate similarity
    matcher = SequenceMatcher(None, old_lines, new_lines)
    similarity = round(matcher.ratio(), 3)

    return DiffResult(
        diff_type=diff_type,
        diff_output=diff_output,
        changes=changes,
        additions=sum(1 for c in changes if c.type == "add"),
        deletions=sum(1 for c in changes if c.type == "remove"),
        unchanged=sum(1 for c in changes if c.type == "equal"),
        similarity=similarity,
        old_content=old,
        new_content=new,
    )


def _parse_diff_changes(
    _old_lines: list[str], _new_lines: list[str], diff_lines: list[str]
) -> list[DiffLine]:
    """Parse diff lines into DiffLine objects."""
    changes: list[DiffLine] = []
    old_idx = 0
    new_idx = 0

    for line in diff_lines:
        if line.startswith("---") or line.startswith("+++"):
            continue
        elif line.startswith("@@"):
            # Parse line numbers from context header
            # @@ -old_start,old_count +new_start,new_count @@
            parts = line[3:-3].split()
            if len(parts) >= 2:
                old_part = parts[0].split(",")[0].lstrip("-")
                new_part = parts[1].split(",")[0].lstrip("+")
                old_idx = int(old_part) - 1 if old_part else 0
                new_idx = int(new_part) - 1 if new_part else 0
            continue

        if line.startswith("+") and not line.startswith("+++"):
            changes.append(
                DiffLine(
                    type="add",
                    content=line[1:],
                    line_number_old=None,
                    line_number_new=new_idx + 1,
                )
            )
            new_idx += 1
        elif line.startswith("-") and not line.startswith("---"):
            changes.append(
                DiffLine(
                    type="remove",
                    content=line[1:],
                    line_number_old=old_idx + 1,
                    line_number_new=None,
                )
            )
            old_idx += 1
        elif line.startswith(" "):
            changes.append(
                DiffLine(
                    type="equal",
                    content=line[1:],
                    line_number_old=old_idx + 1,
                    line_number_new=new_idx + 1,
                )
            )
            old_idx += 1
            new_idx += 1

    return changes


def diff_json(
    old: dict[str, Any] | list[Any] | None,
    new: dict[str, Any] | list[Any] | None,
) -> DiffResult:
    """Generate a JSON Patch-style diff between two JSON-ifiable objects.

    Args:
        old: Original JSON-ifiable object (dict, list, or None)
        new: New JSON-ifiable object (dict, list, or None)

    Returns:
        DiffResult with JSON Patch operations

    Example:
        ```python
        old = {"name": "Alice", "age": 30}
        new = {"name": "Alice", "age": 31, "city": "NYC"}
        result = diff_json(old, new)
        print(result.diff_output)
        # [
        #   {"op": "replace", "path": "/age", "value": 31},
        #   {"op": "add", "path": "/city", "value": "NYC"}
        # ]
        ```
    """
    import json

    patch_ops = _generate_json_patch(old or {}, new or {})

    # Build human-readable diff output
    lines = ["["]
    for i, op in enumerate(patch_ops):
        comma = "," if i < len(patch_ops) - 1 else ""
        lines.append(f'  {json.dumps(op)}{comma}')
    lines.append("]")
    diff_output = "\n".join(lines)

    # Count operations by type
    additions = sum(1 for op in patch_ops if op["op"] in ("add", "replace"))
    deletions = sum(1 for op in patch_ops if op["op"] == "remove")

    return DiffResult(
        diff_type=DiffType.JSON_PATCH,
        diff_output=diff_output,
        additions=additions,
        deletions=deletions,
        changes=[],
        similarity=_calculate_json_similarity(old, new),
        old_content=json.dumps(old, indent=2) if old is not None else None,
        new_content=json.dumps(new, indent=2) if new is not None else None,
    )


def _generate_json_patch(
    old: dict[str, Any] | list[Any], new: dict[str, Any] | list[Any]
) -> list[dict[str, Any]]:
    """Generate JSON Patch operations from two objects."""

    patch: list[dict[str, Any]] = []

    if isinstance(old, dict) and isinstance(new, dict):
        # Find removed keys
        for key in old:
            if key not in new:
                patch.append({"op": "remove", "path": f"/{key}"})

        # Find added and modified keys
        for key in new:
            if key not in old:
                patch.append({"op": "add", "path": f"/{key}", "value": new[key]})
            elif old[key] != new[key]:
                old_val = old[key]
                new_val = new[key]

                # Recurse into nested objects/arrays
                if isinstance(old_val, (dict, list)) and isinstance(new_val, (dict, list)):
                    sub_patch = _generate_json_patch(old_val, new_val)
                    for op in sub_patch:
                        op["path"] = f"/{key}{op['path']}"
                    patch.extend(sub_patch)
                else:
                    patch.append({"op": "replace", "path": f"/{key}", "value": new_val})

    elif isinstance(old, list) and isinstance(new, list):
        # Compare lists
        max_len = max(len(old), len(new))
        for i in range(max_len):
            if i >= len(old):
                patch.append({"op": "add", "path": f"/{i}", "value": new[i]})
            elif i >= len(new):
                patch.append({"op": "remove", "path": f"/{i}"})
            elif old[i] != new[i]:
                old_val = old[i]
                new_val = new[i]
                if isinstance(old_val, (dict, list)) and isinstance(new_val, (dict, list)):
                    sub_patch = _generate_json_patch(old_val, new_val)
                    for op in sub_patch:
                        op["path"] = f"/{i}{op['path']}"
                    patch.extend(sub_patch)
                else:
                    patch.append({"op": "replace", "path": f"/{i}", "value": new_val})

    return patch


def _calculate_json_similarity(
    old: dict[str, Any] | list[Any] | None,
    new: dict[str, Any] | list[Any] | None,
) -> float:
    """Calculate similarity ratio between two JSON objects."""
    if old is None and new is None:
        return 1.0
    if old is None or new is None:
        return 0.0

    import json

    old_str = json.dumps(old, sort_keys=True)
    new_str = json.dumps(new, sort_keys=True)

    matcher = SequenceMatcher(None, old_str, new_str)
    return round(matcher.ratio(), 3)


def diff_structured(
    old: dict[str, Any],
    new: dict[str, Any],
    ignore_keys: set[str] | None = None,
) -> DiffResult:
    """Generate a structured diff between two dictionaries.

    This provides a more detailed view of what changed in a dict-like structure,
    suitable for displaying to users or logging.

    Args:
        old: Original dictionary
        new: New dictionary
        ignore_keys: Keys to ignore in comparison

    Returns:
        DiffResult with structured change information

    Example:
        ```python
        old = {"status": "draft", "title": "My Post"}
        new = {"status": "published", "title": "My Post"}
        result = diff_structured(old, new)
        # Changes will contain individual field changes
        ```
    """
    ignore_keys = ignore_keys or set()

    changes: list[DiffLine] = []
    additions = 0
    deletions = 0

    # Find removed keys
    for key in old:
        if key in ignore_keys:
            continue
        if key not in new:
            changes.append(
                DiffLine(
                    type="remove",
                    content=f"{key}: {old[key]!r}",
                    line_number_old=None,
                    line_number_new=None,
                )
            )
            deletions += 1

    # Find added keys
    for key in new:
        if key in ignore_keys:
            continue
        if key not in old:
            changes.append(
                DiffLine(
                    type="add",
                    content=f"{key}: {new[key]!r}",
                    line_number_old=None,
                    line_number_new=None,
                )
            )
            additions += 1

    # Find modified keys
    for key in old:
        if key in ignore_keys or key not in new:
            continue
        if old[key] != new[key]:
            changes.append(
                DiffLine(
                    type="remove",
                    content=f"{key}: {old[key]!r}",
                    line_number_old=None,
                    line_number_new=None,
                )
            )
            changes.append(
                DiffLine(
                    type="add",
                    content=f"{key}: {new[key]!r}",
                    line_number_old=None,
                    line_number_new=None,
                )
            )
            deletions += 1
            additions += 1

    # Build diff output
    lines = ["--- old", "+++ new"]
    for change in changes:
        prefix = "-" if change.type == "remove" else "+" if change.type == "add" else " "
        lines.append(f"{prefix} {change.content}")
    diff_output = "\n".join(lines)

    return DiffResult(
        diff_type=DiffType.LINE_BY_LINE,
        diff_output=diff_output,
        changes=changes,
        additions=additions,
        deletions=deletions,
        similarity=_calculate_json_similarity(old, new),
    )


__all__ = [
    "DiffType",
    "DiffLine",
    "DiffResult",
    "diff_text",
    "diff_json",
    "diff_structured",
]
