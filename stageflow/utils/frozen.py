"""Immutable data structures for safe data sharing.

This module provides FrozenDict and FrozenList for read-only data access,
used in context forking to prevent child pipelines from modifying parent data.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any, TypeVar

K = TypeVar("K")
V = TypeVar("V")
T = TypeVar("T")


class FrozenDict(Mapping[K, V]):
    """Immutable dictionary wrapper.

    Wraps a dictionary and prevents any mutation. Used for sharing
    parent context data with child pipelines in a read-only manner.

    Example:
        data = {"key": "value"}
        frozen = FrozenDict(data)
        frozen["key"]  # Returns "value"
        frozen["key"] = "new"  # Raises TypeError

    Note:
        This is a shallow freeze. Nested mutable objects can still be modified.
        For deep immutability, use copy.deepcopy before wrapping.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[K, V] | None = None) -> None:
        self._data: dict[K, V] = dict(data) if data else {}

    def __getitem__(self, key: K) -> V:
        return self._data[key]

    def __iter__(self) -> Iterator[K]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __repr__(self) -> str:
        return f"FrozenDict({self._data!r})"

    def __hash__(self) -> int:
        return hash(tuple(sorted(self._data.items(), key=lambda x: str(x[0]))))

    def get(self, key: K, default: V | None = None) -> V | None:
        """Get a value with optional default."""
        return self._data.get(key, default)

    def keys(self) -> Any:
        """Return dictionary keys."""
        return self._data.keys()

    def values(self) -> Any:
        """Return dictionary values."""
        return self._data.values()

    def items(self) -> Any:
        """Return dictionary items."""
        return self._data.items()

    def to_dict(self) -> dict[K, V]:
        """Create a mutable copy of the data."""
        return dict(self._data)

    def copy(self) -> FrozenDict[K, V]:
        """Create a new FrozenDict with the same data."""
        return FrozenDict(self._data)


class FrozenList(Sequence[T]):
    """Immutable list wrapper.

    Wraps a list and prevents any mutation. Used for sharing
    sequences in a read-only manner.

    Example:
        items = [1, 2, 3]
        frozen = FrozenList(items)
        frozen[0]  # Returns 1
        frozen[0] = 10  # Raises TypeError
    """

    __slots__ = ("_data",)

    def __init__(self, data: Sequence[T] | None = None) -> None:
        self._data: tuple[T, ...] = tuple(data) if data else ()

    def __getitem__(self, index: int | slice) -> T | Sequence[T]:
        return self._data[index]

    def __iter__(self) -> Iterator[T]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, item: object) -> bool:
        return item in self._data

    def __repr__(self) -> str:
        return f"FrozenList({list(self._data)!r})"

    def __hash__(self) -> int:
        return hash(self._data)

    def to_list(self) -> list[T]:
        """Create a mutable copy of the data."""
        return list(self._data)

    def copy(self) -> FrozenList[T]:
        """Create a new FrozenList with the same data."""
        return FrozenList(self._data)


__all__ = [
    "FrozenDict",
    "FrozenList",
]
