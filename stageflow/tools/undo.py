"""Undo metadata storage for reversible tool actions.

This module provides in-memory storage for undo metadata with TTL support.
Production implementations can extend or replace with Redis/DB storage.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from .definitions import UndoMetadata


@dataclass
class UndoEntry:
    """Internal entry with expiration tracking."""

    metadata: UndoMetadata
    expires_at: datetime


class UndoStore:
    """In-memory store for undo metadata with TTL.

    This is a simple in-memory implementation suitable for testing and
    single-instance deployments. For production, consider:
    - Redis-based implementation with native TTL
    - Database-backed implementation with periodic cleanup

    Attributes:
        default_ttl_seconds: Default time-to-live for entries (1 hour)
    """

    def __init__(self, default_ttl_seconds: float = 3600.0) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self._entries: dict[UUID, UndoEntry] = {}
        self._lock = asyncio.Lock()

    async def store(
        self,
        action_id: UUID,
        tool_name: str,
        undo_data: dict[str, Any],
        ttl_seconds: float | None = None,
    ) -> UndoMetadata:
        """Store undo metadata for an action.

        Args:
            action_id: The action identifier
            tool_name: Name of the tool
            undo_data: Tool-specific undo data
            ttl_seconds: Time-to-live in seconds (None uses default)

        Returns:
            The stored UndoMetadata
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl)

        metadata = UndoMetadata(
            action_id=action_id,
            tool_name=tool_name,
            undo_data=undo_data,
        )

        async with self._lock:
            self._entries[action_id] = UndoEntry(
                metadata=metadata,
                expires_at=expires_at,
            )

        return metadata

    async def get(self, action_id: UUID) -> UndoMetadata | None:
        """Retrieve undo metadata for an action.

        Args:
            action_id: The action identifier

        Returns:
            UndoMetadata if found and not expired, None otherwise
        """
        async with self._lock:
            entry = self._entries.get(action_id)
            if entry is None:
                return None

            if datetime.now(UTC) > entry.expires_at:
                del self._entries[action_id]
                return None

            return entry.metadata

    async def delete(self, action_id: UUID) -> bool:
        """Delete undo metadata for an action.

        Args:
            action_id: The action identifier

        Returns:
            True if entry was deleted, False if not found
        """
        async with self._lock:
            if action_id in self._entries:
                del self._entries[action_id]
                return True
            return False

    async def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed
        """
        now = datetime.now(UTC)
        removed = 0

        async with self._lock:
            expired = [
                action_id
                for action_id, entry in self._entries.items()
                if now > entry.expires_at
            ]
            for action_id in expired:
                del self._entries[action_id]
                removed += 1

        return removed

    async def get_all(self) -> list[UndoMetadata]:
        """Get all non-expired entries.

        Returns:
            List of all valid UndoMetadata entries
        """
        now = datetime.now(UTC)
        async with self._lock:
            return [
                entry.metadata
                for entry in self._entries.values()
                if now <= entry.expires_at
            ]

    def __len__(self) -> int:
        """Return number of entries (may include expired)."""
        return len(self._entries)


# Global undo store instance
_undo_store: UndoStore | None = None


def get_undo_store() -> UndoStore:
    """Get the global undo store instance."""
    global _undo_store
    if _undo_store is None:
        _undo_store = UndoStore()
    return _undo_store


def set_undo_store(store: UndoStore) -> None:
    """Set the global undo store instance."""
    global _undo_store
    _undo_store = store


def clear_undo_store() -> None:
    """Clear the global undo store instance."""
    global _undo_store
    _undo_store = None


__all__ = [
    "UndoStore",
    "UndoEntry",
    "get_undo_store",
    "set_undo_store",
    "clear_undo_store",
]
