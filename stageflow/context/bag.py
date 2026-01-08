"""ContextBag for thread-safe output storage with conflict detection.

This module provides the ContextBag class for safe parallel stage execution,
detecting and rejecting duplicate key writes from different stages.
"""

from __future__ import annotations

import asyncio
from typing import Any


class DataConflictError(Exception):
    """Raised when multiple stages attempt to write the same key.

    Attributes:
        key: The conflicting key
        existing_writer: Stage that first wrote the key
        new_writer: Stage attempting to overwrite
    """

    def __init__(self, key: str, existing_writer: str, new_writer: str) -> None:
        self.key = key
        self.existing_writer = existing_writer
        self.new_writer = new_writer
        super().__init__(
            f"Key '{key}' already written by '{existing_writer}', "
            f"cannot write from '{new_writer}'"
        )


class ContextBag:
    """Thread-safe output bag with conflict detection.

    Provides a safe mechanism for parallel stages to write outputs
    without overwriting each other. Detects and rejects duplicate
    key writes from different stages.

    Example:
        bag = ContextBag()
        await bag.write("user_message", "hello", "stt_stage")
        value = bag.read("user_message")  # Returns "hello"

        # This would raise DataConflictError:
        await bag.write("user_message", "world", "other_stage")
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._writers: dict[str, str] = {}  # key -> stage_name

    async def write(self, key: str, value: Any, stage_name: str) -> None:
        """Write a key-value pair, rejecting duplicates.

        Args:
            key: The key to write
            value: The value to store
            stage_name: Name of the stage performing the write

        Raises:
            DataConflictError: If key was already written by another stage
        """
        async with self._lock:
            if key in self._data:
                raise DataConflictError(
                    key=key,
                    existing_writer=self._writers[key],
                    new_writer=stage_name,
                )
            self._data[key] = value
            self._writers[key] = stage_name

    def read(self, key: str, default: Any = None) -> Any:
        """Read a value (no lock needed for reads).

        Args:
            key: The key to read
            default: Value to return if key not found

        Returns:
            The stored value or default
        """
        return self._data.get(key, default)

    def has(self, key: str) -> bool:
        """Check if a key exists.

        Args:
            key: The key to check

        Returns:
            True if key exists, False otherwise
        """
        return key in self._data

    def keys(self) -> list[str]:
        """Get all stored keys.

        Returns:
            List of all keys in the bag
        """
        return list(self._data.keys())

    def get_writer(self, key: str) -> str | None:
        """Get the stage that wrote a specific key.

        Args:
            key: The key to look up

        Returns:
            Stage name that wrote the key, or None if not found
        """
        return self._writers.get(key)

    def to_dict(self) -> dict[str, Any]:
        """Convert bag contents to a dictionary.

        Returns:
            Copy of the internal data dictionary
        """
        return self._data.copy()

    def __repr__(self) -> str:
        return f"ContextBag(keys={list(self._data.keys())})"


__all__ = [
    "ContextBag",
    "DataConflictError",
]
