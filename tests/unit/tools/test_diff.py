"""Unit tests for diff utilities."""

from __future__ import annotations

from stageflow.tools.diff import (
    DiffLine,
    DiffResult,
    DiffType,
    diff_json,
    diff_structured,
    diff_text,
)


class TestDiffType:
    """Tests for DiffType enum."""

    def test_diff_type_values(self) -> None:
        """DiffType has expected values."""
        assert DiffType.UNIFIED.value == "unified"
        assert DiffType.CONTEXT.value == "context"
        assert DiffType.JSON_PATCH.value == "json_patch"
        assert DiffType.LINE_BY_LINE.value == "line_by_line"


class TestDiffLine:
    """Tests for DiffLine dataclass."""

    def test_create_diff_line(self) -> None:
        """Create a DiffLine."""
        line = DiffLine(
            type="add",
            content="+ New line",
            line_number_old=None,
            line_number_new=5,
        )
        assert line.type == "add"
        assert line.content == "+ New line"
        assert line.line_number_old is None
        assert line.line_number_new == 5

    def test_diff_line_to_dict(self) -> None:
        """DiffLine serializes to dictionary."""
        line = DiffLine(
            type="equal",
            content="  existing",
            line_number_old=3,
            line_number_new=3,
        )
        result = line.to_dict()
        assert result["type"] == "equal"
        assert result["content"] == "  existing"
        assert result["line_number_old"] == 3
        assert result["line_number_new"] == 3


class TestDiffResult:
    """Tests for DiffResult dataclass."""

    def test_create_diff_result(self) -> None:
        """Create a DiffResult."""
        result = DiffResult(
            diff_type=DiffType.UNIFIED,
            diff_output="--- old\n+++ new",
            changes=[],
            additions=1,
            deletions=0,
            unchanged=5,
            similarity=0.9,
        )
        assert result.diff_type == DiffType.UNIFIED
        assert result.additions == 1
        assert result.deletions == 0
        assert result.similarity == 0.9

    def test_has_changes_true(self) -> None:
        """has_changes returns True when there are additions."""
        result = DiffResult(
            diff_type=DiffType.UNIFIED,
            diff_output="",
            additions=1,
            deletions=0,
            changes=[],
        )
        assert result.has_changes is True

    def test_has_changes_true_deletions(self) -> None:
        """has_changes returns True when there are deletions."""
        result = DiffResult(
            diff_type=DiffType.UNIFIED,
            diff_output="",
            additions=0,
            deletions=1,
            changes=[],
        )
        assert result.has_changes is True

    def test_has_changes_false(self) -> None:
        """has_changes returns False when no changes."""
        result = DiffResult(
            diff_type=DiffType.UNIFIED,
            diff_output="",
            additions=0,
            deletions=0,
            changes=[],
        )
        assert result.has_changes is False

    def test_change_summary_no_changes(self) -> None:
        """change_summary returns 'no changes' when unchanged."""
        result = DiffResult(
            diff_type=DiffType.UNIFIED,
            diff_output="",
            additions=0,
            deletions=0,
            changes=[],
        )
        assert result.change_summary == "no changes"

    def test_change_summary_additions(self) -> None:
        """change_summary shows additions."""
        result = DiffResult(
            diff_type=DiffType.UNIFIED,
            diff_output="",
            additions=3,
            deletions=0,
            changes=[],
        )
        assert result.change_summary == "+3"

    def test_change_summary_deletions(self) -> None:
        """change_summary shows deletions."""
        result = DiffResult(
            diff_type=DiffType.UNIFIED,
            diff_output="",
            additions=0,
            deletions=2,
            changes=[],
        )
        assert result.change_summary == "-2"

    def test_change_summary_mixed(self) -> None:
        """change_summary shows both additions and deletions."""
        result = DiffResult(
            diff_type=DiffType.UNIFIED,
            diff_output="",
            additions=5,
            deletions=3,
            changes=[],
        )
        assert result.change_summary == "+5 -3"

    def test_diff_result_to_dict(self) -> None:
        """DiffResult serializes to dictionary."""
        result = DiffResult(
            diff_type=DiffType.UNIFIED,
            diff_output="--- old\n+++ new",
            changes=[
                DiffLine(type="add", content="+ added", line_number_old=None, line_number_new=1)
            ],
            additions=1,
            deletions=0,
            unchanged=0,
            similarity=0.5,
        )
        serialized = result.to_dict()
        assert serialized["diff_type"] == "unified"
        assert serialized["additions"] == 1
        assert serialized["deletions"] == 0
        assert len(serialized["changes"]) == 1


class TestDiffText:
    """Tests for diff_text function."""

    def test_identical_content(self) -> None:
        """diff_text returns no changes for identical content."""
        content = "Hello\nWorld"
        result = diff_text(content, content)
        assert result.has_changes is False
        assert result.additions == 0
        assert result.deletions == 0
        assert result.similarity == 1.0

    def test_add_lines(self) -> None:
        """diff_text detects added lines."""
        old = "Hello\nWorld"
        new = "Hello\nPython\nWorld"
        result = diff_text(old, new)
        assert result.has_changes is True
        assert result.additions == 1
        assert result.deletions == 0
        assert "+Python" in result.diff_output

    def test_remove_lines(self) -> None:
        """diff_text detects removed lines."""
        old = "Hello\nPython\nWorld"
        new = "Hello\nWorld"
        result = diff_text(old, new)
        assert result.has_changes is True
        assert result.additions == 0
        assert result.deletions == 1
        assert "-Python" in result.diff_output

    def test_modify_lines(self) -> None:
        """diff_text detects line modifications."""
        old = "Hello\nWorld"
        new = "Hello\nPython"
        result = diff_text(old, new)
        assert result.has_changes is True
        assert result.additions == 1
        assert result.deletions == 1

    def test_empty_to_content(self) -> None:
        """diff_text handles empty to content."""
        result = diff_text("", "Hello\nWorld")
        assert result.has_changes is True
        assert result.additions == 2

    def test_content_to_empty(self) -> None:
        """diff_text handles content to empty."""
        result = diff_text("Hello\nWorld", "")
        assert result.has_changes is True
        assert result.deletions == 2

    def test_unified_diff_format(self) -> None:
        """diff_text generates unified diff format."""
        result = diff_text("old", "new")
        assert "--- a/original" in result.diff_output
        assert "+++ b/modified" in result.diff_output

    def test_custom_filenames(self) -> None:
        """diff_text uses custom filenames."""
        result = diff_text("old", "new", fromfile="before.txt", tofile="after.txt")
        assert "--- before.txt" in result.diff_output
        assert "+++ after.txt" in result.diff_output

    def test_custom_context_lines(self) -> None:
        """diff_text respects context_lines parameter."""
        old = "line1\nline2\nline3\nline4\nline5"
        new = "line1\nline2\nCHANGED\nline4\nline5"
        result = diff_text(old, new, context_lines=5)
        # Should have more context lines around the change
        assert result.changes  # Has changes

    def test_changes_parsed(self) -> None:
        """diff_text parses changes correctly."""
        old = "a\nb\nc"
        new = "a\nX\nc"
        result = diff_text(old, new)
        assert len(result.changes) >= 2  # At least remove old and add new
        # Check that we have both types of changes
        change_types = {c.type for c in result.changes}
        assert "remove" in change_types
        assert "add" in change_types


class TestDiffJson:
    """Tests for diff_json function."""

    def test_identical_dicts(self) -> None:
        """diff_json returns no changes for identical dicts."""
        data = {"name": "Alice", "age": 30}
        result = diff_json(data, data)
        assert result.has_changes is False
        assert result.additions == 0
        assert result.deletions == 0

    def test_added_key(self) -> None:
        """diff_json detects added keys."""
        old = {"name": "Alice"}
        new = {"name": "Alice", "city": "NYC"}
        result = diff_json(old, new)
        assert result.has_changes is True
        assert result.additions == 1
        assert '"op": "add"' in result.diff_output
        assert '"/city"' in result.diff_output

    def test_removed_key(self) -> None:
        """diff_json detects removed keys."""
        old = {"name": "Alice", "city": "NYC"}
        new = {"name": "Alice"}
        result = diff_json(old, new)
        assert result.has_changes is True
        assert result.deletions == 1
        assert '"op": "remove"' in result.diff_output

    def test_modified_value(self) -> None:
        """diff_json detects modified values."""
        old = {"age": 30}
        new = {"age": 31}
        result = diff_json(old, new)
        assert result.has_changes is True
        assert '"op": "replace"' in result.diff_output

    def test_nested_dict(self) -> None:
        """diff_json handles nested dicts."""
        old = {"user": {"name": "Alice", "age": 30}}
        new = {"user": {"name": "Alice", "age": 31}}
        result = diff_json(old, new)
        assert result.has_changes is True
        assert '"/user/age"' in result.diff_output

    def test_array_modification(self) -> None:
        """diff_json handles array modifications."""
        old = {"items": [1, 2, 3]}
        new = {"items": [1, 2, 3, 4]}
        result = diff_json(old, new)
        assert result.has_changes is True

    def test_null_handling(self) -> None:
        """diff_json handles None values."""
        result = diff_json(None, {"key": "value"})
        assert result.has_changes is True
        result2 = diff_json({"key": "value"}, None)
        assert result2.has_changes is True


class TestDiffStructured:
    """Tests for diff_structured function."""

    def test_identical_dicts(self) -> None:
        """diff_structured returns no changes for identical dicts."""
        data = {"status": "active", "count": 5}
        result = diff_structured(data, data)
        assert result.has_changes is False

    def test_added_field(self) -> None:
        """diff_structured detects added fields."""
        old = {"name": "Alice"}
        new = {"name": "Alice", "age": 30}
        result = diff_structured(old, new)
        assert result.has_changes is True
        assert result.additions == 1

    def test_removed_field(self) -> None:
        """diff_structured detects removed fields."""
        old = {"name": "Alice", "age": 30}
        new = {"name": "Alice"}
        result = diff_structured(old, new)
        assert result.has_changes is True
        assert result.deletions == 1

    def test_modified_field(self) -> None:
        """diff_structured shows both remove and add for modifications."""
        old = {"status": "pending"}
        new = {"status": "done"}
        result = diff_structured(old, new)
        assert result.has_changes is True
        assert result.additions == 1
        assert result.deletions == 1
        # Check the diff output format
        assert "- status: 'pending'" in result.diff_output
        assert "+ status: 'done'" in result.diff_output

    def test_ignore_keys(self) -> None:
        """diff_structured respects ignore_keys."""
        old = {"id": 1, "status": "pending"}
        new = {"id": 2, "status": "done"}
        result = diff_structured(old, new, ignore_keys={"id"})
        assert result.has_changes is True
        assert result.additions == 1
        assert result.deletions == 1

    def test_ignore_allows_identical(self) -> None:
        """diff_structured with ignored keys that differ shows no changes."""
        old = {"id": 1, "status": "done"}
        new = {"id": 2, "status": "done"}
        result = diff_structured(old, new, ignore_keys={"id"})
        assert result.has_changes is False

    def test_empty_dicts(self) -> None:
        """diff_structured handles empty dicts."""
        result = diff_structured({}, {})
        assert result.has_changes is False

    def test_complex_values(self) -> None:
        """diff_structured handles complex values."""
        old = {"list": [1, 2, 3], "nested": {"a": 1}}
        new = {"list": [1, 2, 3], "nested": {"a": 2}}
        result = diff_structured(old, new)
        assert result.has_changes is True


class TestDiffIntegration:
    """Integration tests for diff utilities with tools."""

    def test_diff_result_for_undo_metadata(self) -> None:
        """DiffResult can be serialized for undo metadata."""
        old = "original content"
        new = "modified content"
        result = diff_text(old, new)

        # Serialize for storage
        serialized = result.to_dict()

        # Verify structure
        assert "diff_type" in serialized
        assert "diff_output" in serialized
        assert "additions" in serialized
        assert "deletions" in serialized

        # Should be storable and retrievable
        assert serialized["additions"] == result.additions
        assert serialized["deletions"] == result.deletions

    def test_multiple_diff_types_for_same_content(self) -> None:
        """Same content can generate different diff types."""
        old = {"name": "Alice"}
        new = {"name": "Alice", "city": "NYC"}

        text_diff = diff_text(str(old), str(new))
        json_diff = diff_json(old, new)

        assert text_diff.has_changes is True
        assert json_diff.has_changes is True
        assert text_diff.diff_type != json_diff.diff_type
