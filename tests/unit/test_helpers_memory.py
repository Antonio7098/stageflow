"""Tests for the memory helper module."""

from __future__ import annotations

import pytest
from uuid import uuid4
from datetime import UTC, datetime

from stageflow.helpers.memory import (
    MemoryConfig,
    MemoryEntry,
    MemoryFetchStage,
    MemoryWriteStage,
    InMemoryStore,
)
from stageflow.core import StageOutput, StageStatus
from stageflow.testing import create_test_stage_context, create_test_snapshot
from stageflow.stages.inputs import create_stage_inputs


class TestMemoryEntry:
    """Tests for MemoryEntry dataclass."""

    def test_to_dict(self):
        """Should serialize to dictionary."""
        session_id = uuid4()
        entry = MemoryEntry(
            id="test-1",
            session_id=session_id,
            role="user",
            content="Hello",
            metadata={"key": "value"},
        )

        result = entry.to_dict()

        assert result["id"] == "test-1"
        assert result["session_id"] == str(session_id)
        assert result["role"] == "user"
        assert result["content"] == "Hello"
        assert result["metadata"] == {"key": "value"}
        assert "timestamp" in result

    def test_from_dict(self):
        """Should deserialize from dictionary."""
        session_id = uuid4()
        data = {
            "id": "test-1",
            "session_id": str(session_id),
            "role": "assistant",
            "content": "Hello back",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "metadata": {},
        }

        entry = MemoryEntry.from_dict(data)

        assert entry.id == "test-1"
        assert entry.session_id == session_id
        assert entry.role == "assistant"
        assert entry.content == "Hello back"


class TestInMemoryStore:
    """Tests for InMemoryStore."""

    @pytest.mark.asyncio
    async def test_write_and_fetch(self):
        """Should write and fetch entries."""
        store = InMemoryStore()
        session_id = uuid4()

        entry = MemoryEntry(
            id="1",
            session_id=session_id,
            role="user",
            content="Hello",
        )

        await store.write(entry)
        result = await store.fetch(session_id, MemoryConfig())

        assert len(result) == 1
        assert result[0].content == "Hello"

    @pytest.mark.asyncio
    async def test_fetch_respects_max_entries(self):
        """Should limit entries by max_entries."""
        store = InMemoryStore()
        session_id = uuid4()

        # Write 10 entries
        for i in range(10):
            await store.write(MemoryEntry(
                id=str(i),
                session_id=session_id,
                role="user",
                content=f"Message {i}",
            ))

        result = await store.fetch(session_id, MemoryConfig(max_entries=5))

        assert len(result) == 5
        # Should get the most recent 5
        assert result[-1].content == "Message 9"

    @pytest.mark.asyncio
    async def test_fetch_filters_system_messages(self):
        """Should filter system messages when configured."""
        store = InMemoryStore()
        session_id = uuid4()

        await store.write(MemoryEntry(id="1", session_id=session_id, role="user", content="Hi"))
        await store.write(MemoryEntry(id="2", session_id=session_id, role="system", content="System"))
        await store.write(MemoryEntry(id="3", session_id=session_id, role="assistant", content="Hello"))

        result = await store.fetch(session_id, MemoryConfig(include_system=False))

        assert len(result) == 2
        assert all(e.role != "system" for e in result)

    @pytest.mark.asyncio
    async def test_clear(self):
        """Should clear all entries for a session."""
        store = InMemoryStore()
        session_id = uuid4()

        await store.write(MemoryEntry(id="1", session_id=session_id, role="user", content="Hi"))
        await store.write(MemoryEntry(id="2", session_id=session_id, role="user", content="Hello"))

        count = await store.clear(session_id)

        assert count == 2
        result = await store.fetch(session_id, MemoryConfig())
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_isolation_between_sessions(self):
        """Different sessions should be isolated."""
        store = InMemoryStore()
        session_a = uuid4()
        session_b = uuid4()

        await store.write(MemoryEntry(id="1", session_id=session_a, role="user", content="A"))
        await store.write(MemoryEntry(id="2", session_id=session_b, role="user", content="B"))

        result_a = await store.fetch(session_a, MemoryConfig())
        result_b = await store.fetch(session_b, MemoryConfig())

        assert len(result_a) == 1
        assert result_a[0].content == "A"
        assert len(result_b) == 1
        assert result_b[0].content == "B"


class TestMemoryFetchStage:
    """Tests for MemoryFetchStage."""

    @pytest.mark.asyncio
    async def test_fetches_memory(self):
        """Should fetch memory entries."""
        store = InMemoryStore()
        session_id = uuid4()

        await store.write(MemoryEntry(
            id="1", session_id=session_id, role="user", content="Hello"
        ))

        stage = MemoryFetchStage(store)
        ctx = create_test_stage_context(session_id=session_id)

        result = await stage.execute(ctx)

        assert result.status == StageStatus.OK
        assert result.data["memory_count"] == 1
        assert len(result.data["memory_entries"]) == 1

    @pytest.mark.asyncio
    async def test_skips_without_session_id(self):
        """Should skip if no session_id."""
        store = InMemoryStore()
        stage = MemoryFetchStage(store)

        snapshot = create_test_snapshot(session_id=None)
        ctx = create_test_stage_context(snapshot=snapshot)

        result = await stage.execute(ctx)

        assert result.status == StageStatus.SKIP


class TestMemoryWriteStage:
    """Tests for MemoryWriteStage."""

    @pytest.mark.asyncio
    async def test_writes_exchange(self):
        """Should write user input and LLM response."""
        store = InMemoryStore()
        session_id = uuid4()

        stage = MemoryWriteStage(store, response_stage="llm", response_key="response")

        ctx = create_test_stage_context(
            session_id=session_id,
            input_text="Hello",
            interaction_id=uuid4(),
            prior_outputs={
                "llm": StageOutput.ok(response="Hello back!"),
            },
            declared_deps=frozenset({"llm"}),
        )

        result = await stage.execute(ctx)

        assert result.status == StageStatus.OK
        assert result.data["entries_written"] == 2

        # Verify entries in store
        entries = await store.fetch(session_id, MemoryConfig())
        assert len(entries) == 2
        assert entries[0].role == "user"
        assert entries[1].role == "assistant"
