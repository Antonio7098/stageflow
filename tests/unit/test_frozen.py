"""Unit tests for FrozenDict and FrozenList utilities."""

from __future__ import annotations

import pytest

from stageflow.utils.frozen import FrozenDict, FrozenList


class TestFrozenDict:
    """Tests for FrozenDict immutable dictionary wrapper."""

    def test_create_from_dict(self) -> None:
        """Create FrozenDict from regular dict."""
        data = {"a": 1, "b": 2}
        frozen = FrozenDict(data)

        assert frozen["a"] == 1
        assert frozen["b"] == 2

    def test_create_empty(self) -> None:
        """Create empty FrozenDict."""
        frozen = FrozenDict()
        assert len(frozen) == 0

    def test_len(self) -> None:
        """len() returns number of items."""
        frozen = FrozenDict({"a": 1, "b": 2, "c": 3})
        assert len(frozen) == 3

    def test_contains(self) -> None:
        """in operator works."""
        frozen = FrozenDict({"key": "value"})
        assert "key" in frozen
        assert "missing" not in frozen

    def test_get_with_default(self) -> None:
        """get() returns default for missing keys."""
        frozen = FrozenDict({"a": 1})
        assert frozen.get("a") == 1
        assert frozen.get("missing") is None
        assert frozen.get("missing", "default") == "default"

    def test_keys_values_items(self) -> None:
        """keys(), values(), items() work correctly."""
        data = {"a": 1, "b": 2}
        frozen = FrozenDict(data)

        assert list(frozen.keys()) == ["a", "b"]
        assert list(frozen.values()) == [1, 2]
        assert list(frozen.items()) == [("a", 1), ("b", 2)]

    def test_iter(self) -> None:
        """Iteration yields keys."""
        frozen = FrozenDict({"a": 1, "b": 2})
        assert list(frozen) == ["a", "b"]

    def test_to_dict_creates_mutable_copy(self) -> None:
        """to_dict() returns a mutable copy."""
        frozen = FrozenDict({"a": 1})
        mutable = frozen.to_dict()

        mutable["a"] = 99
        assert frozen["a"] == 1  # Original unchanged

    def test_copy_creates_new_frozen(self) -> None:
        """copy() creates a new FrozenDict."""
        frozen1 = FrozenDict({"a": 1})
        frozen2 = frozen1.copy()

        assert frozen1 is not frozen2
        assert frozen1["a"] == frozen2["a"]

    def test_repr(self) -> None:
        """repr() includes content."""
        frozen = FrozenDict({"a": 1})
        assert "FrozenDict" in repr(frozen)
        assert "a" in repr(frozen)

    def test_hash(self) -> None:
        """FrozenDict is hashable."""
        frozen = FrozenDict({"a": 1, "b": 2})
        # Should not raise
        hash_value = hash(frozen)
        assert isinstance(hash_value, int)

    def test_original_dict_not_modified(self) -> None:
        """Creating FrozenDict doesn't modify original."""
        original = {"a": 1}
        frozen = FrozenDict(original)

        original["a"] = 99
        assert frozen["a"] == 1  # FrozenDict has its own copy


class TestFrozenList:
    """Tests for FrozenList immutable list wrapper."""

    def test_create_from_list(self) -> None:
        """Create FrozenList from regular list."""
        data = [1, 2, 3]
        frozen = FrozenList(data)

        assert frozen[0] == 1
        assert frozen[1] == 2
        assert frozen[2] == 3

    def test_create_empty(self) -> None:
        """Create empty FrozenList."""
        frozen = FrozenList()
        assert len(frozen) == 0

    def test_len(self) -> None:
        """len() returns number of items."""
        frozen = FrozenList([1, 2, 3])
        assert len(frozen) == 3

    def test_contains(self) -> None:
        """in operator works."""
        frozen = FrozenList([1, 2, 3])
        assert 2 in frozen
        assert 99 not in frozen

    def test_iter(self) -> None:
        """Iteration yields items."""
        frozen = FrozenList([1, 2, 3])
        assert list(frozen) == [1, 2, 3]

    def test_slicing(self) -> None:
        """Slicing works."""
        frozen = FrozenList([1, 2, 3, 4, 5])
        assert frozen[1:3] == (2, 3)

    def test_to_list_creates_mutable_copy(self) -> None:
        """to_list() returns a mutable copy."""
        frozen = FrozenList([1, 2, 3])
        mutable = frozen.to_list()

        mutable[0] = 99
        assert frozen[0] == 1  # Original unchanged

    def test_copy_creates_new_frozen(self) -> None:
        """copy() creates a new FrozenList."""
        frozen1 = FrozenList([1, 2, 3])
        frozen2 = frozen1.copy()

        assert frozen1 is not frozen2
        assert list(frozen1) == list(frozen2)

    def test_repr(self) -> None:
        """repr() includes content."""
        frozen = FrozenList([1, 2])
        assert "FrozenList" in repr(frozen)

    def test_hash(self) -> None:
        """FrozenList is hashable."""
        frozen = FrozenList([1, 2, 3])
        hash_value = hash(frozen)
        assert isinstance(hash_value, int)

    def test_original_list_not_modified(self) -> None:
        """Creating FrozenList doesn't affect original."""
        original = [1, 2, 3]
        frozen = FrozenList(original)

        original[0] = 99
        assert frozen[0] == 1  # FrozenList has its own copy
