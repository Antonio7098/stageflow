"""Chat memory management stages and utilities.

This module provides reusable stages for fetching and writing conversation
memory, enabling stateful chat pipelines without reinventing memory stores.

Usage:
    from stageflow.helpers import MemoryFetchStage, MemoryWriteStage, InMemoryStore

    # Create a memory store
    store = InMemoryStore()

    # Use in pipeline
    pipeline = (
        Pipeline()
        .with_stage("fetch_memory", MemoryFetchStage(store), StageKind.ENRICH)
        .with_stage("llm", LLMStage(), StageKind.TRANSFORM, dependencies=("fetch_memory",))
        .with_stage("write_memory", MemoryWriteStage(store), StageKind.WORK, dependencies=("llm",))
    )
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from stageflow.core import StageContext, StageKind, StageOutput


@dataclass(frozen=True)
class MemoryEntry:
    """A single memory entry.

    Attributes:
        id: Unique identifier for this entry.
        session_id: Session this entry belongs to.
        role: Message role (user, assistant, system).
        content: The message content.
        timestamp: When this entry was created.
        metadata: Additional metadata.
    """

    id: str
    session_id: UUID
    role: str
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "session_id": str(self.session_id),
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            session_id=UUID(data["session_id"]) if isinstance(data["session_id"], str) else data["session_id"],
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data["timestamp"], str) else data["timestamp"],
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class MemoryConfig:
    """Configuration for memory operations.

    Attributes:
        max_entries: Maximum entries to fetch (0 = unlimited).
        max_tokens: Maximum token count to fetch (0 = unlimited).
        include_system: Whether to include system messages.
        recency_window_seconds: Only fetch entries from last N seconds (0 = all).
    """

    max_entries: int = 20
    max_tokens: int = 4000
    include_system: bool = True
    recency_window_seconds: int = 0


class MemoryStore(Protocol):
    """Protocol for memory storage backends.

    Implement this protocol to provide custom storage (Redis, PostgreSQL, etc.).
    """

    async def fetch(
        self,
        session_id: UUID,
        config: MemoryConfig,
    ) -> list[MemoryEntry]:
        """Fetch memory entries for a session.

        Args:
            session_id: The session to fetch memory for.
            config: Configuration for the fetch operation.

        Returns:
            List of memory entries, ordered oldest to newest.
        """
        ...

    async def write(
        self,
        entry: MemoryEntry,
    ) -> None:
        """Write a memory entry.

        Args:
            entry: The entry to store.
        """
        ...

    async def clear(
        self,
        session_id: UUID,
    ) -> int:
        """Clear all memory for a session.

        Args:
            session_id: The session to clear.

        Returns:
            Number of entries deleted.
        """
        ...


class InMemoryStore:
    """In-memory implementation of MemoryStore for testing and prototyping.

    Thread-safe and async-compatible. Data is lost when the process exits.
    Use a persistent store (Redis, PostgreSQL) for production.
    """

    def __init__(self) -> None:
        self._entries: dict[UUID, list[MemoryEntry]] = {}
        self._lock = asyncio.Lock()

    async def fetch(
        self,
        session_id: UUID,
        config: MemoryConfig,
    ) -> list[MemoryEntry]:
        """Fetch memory entries for a session."""
        async with self._lock:
            entries = self._entries.get(session_id, [])

            # Filter by recency if configured
            if config.recency_window_seconds > 0:
                cutoff = datetime.now(UTC).timestamp() - config.recency_window_seconds
                entries = [
                    e for e in entries
                    if e.timestamp.timestamp() > cutoff
                ]

            # Filter system messages if configured
            if not config.include_system:
                entries = [e for e in entries if e.role != "system"]

            # Limit by max_entries
            if config.max_entries > 0:
                entries = entries[-config.max_entries:]

            # Limit by approximate token count (4 chars ~= 1 token)
            if config.max_tokens > 0:
                total_tokens = 0
                limited: list[MemoryEntry] = []
                for entry in reversed(entries):
                    entry_tokens = len(entry.content) // 4
                    if total_tokens + entry_tokens > config.max_tokens:
                        break
                    limited.insert(0, entry)
                    total_tokens += entry_tokens
                entries = limited

            return entries

    async def write(self, entry: MemoryEntry) -> None:
        """Write a memory entry."""
        async with self._lock:
            if entry.session_id not in self._entries:
                self._entries[entry.session_id] = []
            self._entries[entry.session_id].append(entry)

    async def clear(self, session_id: UUID) -> int:
        """Clear all memory for a session."""
        async with self._lock:
            count = len(self._entries.get(session_id, []))
            self._entries.pop(session_id, None)
            return count

    def get_all_sessions(self) -> list[UUID]:
        """Get all session IDs (for testing/debugging)."""
        return list(self._entries.keys())


class MemoryFetchStage:
    """Stage that fetches conversation memory.

    Outputs the fetched memory entries to be used by downstream stages
    (typically an LLM stage for context).

    Output data:
        - memory_entries: List of MemoryEntry dicts
        - memory_count: Number of entries fetched
        - memory_tokens: Approximate token count
    """

    name = "memory_fetch"
    kind = StageKind.ENRICH

    def __init__(
        self,
        store: MemoryStore,
        config: MemoryConfig | None = None,
    ) -> None:
        self._store = store
        self._config = config or MemoryConfig()

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Fetch memory from the store."""
        session_id = ctx.snapshot.session_id

        if session_id is None:
            return StageOutput.skip(reason="No session_id in context")

        entries = await self._store.fetch(session_id, self._config)

        # Calculate approximate token count
        total_tokens = sum(len(e.content) // 4 for e in entries)

        return StageOutput.ok(
            memory_entries=[e.to_dict() for e in entries],
            memory_count=len(entries),
            memory_tokens=total_tokens,
        )


class MemoryWriteStage:
    """Stage that writes the current exchange to memory.

    Reads the user input and assistant response from context/upstream
    and writes them to the memory store.

    Dependencies:
        - Typically depends on an LLM stage to get the assistant response
    """

    name = "memory_write"
    kind = StageKind.WORK

    def __init__(
        self,
        store: MemoryStore,
        *,
        response_stage: str = "llm",
        response_key: str = "response",
    ) -> None:
        self._store = store
        self._response_stage = response_stage
        self._response_key = response_key

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Write the current exchange to memory."""
        session_id = ctx.snapshot.session_id
        if session_id is None:
            return StageOutput.skip(reason="No session_id in context")

        entries_written = 0

        # Write user message
        user_input = ctx.snapshot.input_text
        if user_input:
            user_entry = MemoryEntry(
                id=f"{ctx.snapshot.interaction_id or 'unknown'}_user",
                session_id=session_id,
                role="user",
                content=user_input,
            )
            await self._store.write(user_entry)
            entries_written += 1

        # Write assistant response
        if ctx.inputs:
            response = ctx.inputs.get_from(
                self._response_stage,
                self._response_key,
                default=None,
            )
            if response:
                assistant_entry = MemoryEntry(
                    id=f"{ctx.snapshot.interaction_id or 'unknown'}_assistant",
                    session_id=session_id,
                    role="assistant",
                    content=str(response),
                )
                await self._store.write(assistant_entry)
                entries_written += 1

        return StageOutput.ok(
            entries_written=entries_written,
            session_id=str(session_id),
        )


__all__ = [
    "MemoryConfig",
    "MemoryEntry",
    "MemoryFetchStage",
    "MemoryStore",
    "MemoryWriteStage",
    "InMemoryStore",
]
