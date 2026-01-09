"""Unit tests for undo store."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from stageflow.tools.undo import UndoStore, clear_undo_store, get_undo_store


class TestUndoStore:
    """Tests for UndoStore."""

    @pytest.fixture
    def store(self) -> UndoStore:
        """Create a fresh UndoStore for each test."""
        return UndoStore(default_ttl_seconds=3600)

    @pytest.mark.asyncio
    async def test_store_and_get_metadata(self, store: UndoStore) -> None:
        """Store and retrieve undo metadata."""
        action_id = uuid4()
        metadata = await store.store(
            action_id=action_id,
            tool_name="test_tool",
            undo_data={"original": "content"},
        )

        assert metadata.action_id == action_id
        assert metadata.tool_name == "test_tool"

        retrieved = await store.get(action_id)
        assert retrieved is not None
        assert retrieved.action_id == action_id
        assert retrieved.undo_data == {"original": "content"}

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, store: UndoStore) -> None:
        """Getting nonexistent metadata returns None."""
        result = await store.get(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_metadata(self, store: UndoStore) -> None:
        """Delete undo metadata."""
        action_id = uuid4()
        await store.store(
            action_id=action_id,
            tool_name="test_tool",
            undo_data={},
        )

        deleted = await store.delete(action_id)
        assert deleted is True

        retrieved = await store.get(action_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, store: UndoStore) -> None:
        """Deleting nonexistent returns False."""
        result = await store.delete(uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_expired_entries_not_returned(self) -> None:
        """Expired entries are not returned by get()."""
        store = UndoStore(default_ttl_seconds=0.01)  # 10ms TTL
        action_id = uuid4()

        await store.store(
            action_id=action_id,
            tool_name="test_tool",
            undo_data={},
        )

        # Wait for expiration
        await asyncio.sleep(0.02)

        result = await store.get(action_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_custom_ttl(self, store: UndoStore) -> None:
        """Custom TTL per entry."""
        action_id = uuid4()
        await store.store(
            action_id=action_id,
            tool_name="test_tool",
            undo_data={},
            ttl_seconds=0.01,
        )

        # Should exist immediately
        assert await store.get(action_id) is not None

        # Wait for expiration
        await asyncio.sleep(0.02)

        # Should be expired
        assert await store.get(action_id) is None

    @pytest.mark.asyncio
    async def test_get_all_returns_valid_entries(self, store: UndoStore) -> None:
        """get_all() returns all non-expired entries."""
        ids = [uuid4() for _ in range(3)]

        for i, action_id in enumerate(ids):
            await store.store(
                action_id=action_id,
                tool_name=f"tool_{i}",
                undo_data={"index": i},
            )

        all_entries = await store.get_all()
        assert len(all_entries) == 3

    @pytest.mark.asyncio
    async def test_cleanup_expired(self) -> None:
        """cleanup_expired() removes expired entries."""
        store = UndoStore(default_ttl_seconds=0.01)

        for _ in range(5):
            await store.store(
                action_id=uuid4(),
                tool_name="test",
                undo_data={},
            )

        assert len(store) == 5

        await asyncio.sleep(0.02)
        removed = await store.cleanup_expired()

        assert removed == 5
        assert len(store) == 0

    @pytest.mark.asyncio
    async def test_len_returns_entry_count(self, store: UndoStore) -> None:
        """len() returns number of entries."""
        assert len(store) == 0

        await store.store(uuid4(), "tool", {})
        assert len(store) == 1

        await store.store(uuid4(), "tool", {})
        assert len(store) == 2


class TestUndoStoreGlobals:
    """Tests for global undo store functions."""

    def teardown_method(self) -> None:
        """Clear global store after each test."""
        clear_undo_store()

    def test_get_undo_store_creates_singleton(self) -> None:
        """get_undo_store() returns same instance."""
        store1 = get_undo_store()
        store2 = get_undo_store()
        assert store1 is store2

    def test_clear_undo_store(self) -> None:
        """clear_undo_store() resets the singleton."""
        store1 = get_undo_store()
        clear_undo_store()
        store2 = get_undo_store()
        assert store1 is not store2
