"""Unit tests for ContextBag class."""

import asyncio

import pytest

from stageflow.context.bag import ContextBag, DataConflictError


class TestDataConflictError:
    """Tests for DataConflictError exception."""

    def test_error_contains_key(self):
        """Test that error message contains the conflicting key."""
        error = DataConflictError(
            key="user_message",
            existing_writer="stt_stage",
            new_writer="enricher_stage",
        )
        assert "user_message" in str(error)

    def test_error_contains_stage_names(self):
        """Test that error message contains both stage names."""
        error = DataConflictError(
            key="result",
            existing_writer="first_stage",
            new_writer="second_stage",
        )
        assert "first_stage" in str(error)
        assert "second_stage" in str(error)

    def test_error_attributes(self):
        """Test that error has correct attributes."""
        error = DataConflictError(
            key="data",
            existing_writer="writer1",
            new_writer="writer2",
        )
        assert error.key == "data"
        assert error.existing_writer == "writer1"
        assert error.new_writer == "writer2"


class TestContextBag:
    """Tests for ContextBag class."""

    @pytest.mark.asyncio
    async def test_write_stores_value(self):
        """Test that write() stores value correctly."""
        bag = ContextBag()
        await bag.write("key1", "value1", "stage_a")

        assert bag.read("key1") == "value1"

    @pytest.mark.asyncio
    async def test_read_returns_default_for_missing_key(self):
        """Test that read() returns default for missing key."""
        bag = ContextBag()

        assert bag.read("missing") is None
        assert bag.read("missing", "default") == "default"

    @pytest.mark.asyncio
    async def test_write_same_key_twice_raises_error(self):
        """Test that writing same key twice raises DataConflictError."""
        bag = ContextBag()
        await bag.write("key1", "value1", "stage_a")

        with pytest.raises(DataConflictError) as exc_info:
            await bag.write("key1", "value2", "stage_b")

        assert exc_info.value.key == "key1"
        assert exc_info.value.existing_writer == "stage_a"
        assert exc_info.value.new_writer == "stage_b"

    @pytest.mark.asyncio
    async def test_concurrent_writes_to_different_keys(self):
        """Test that concurrent writes to different keys succeed."""
        bag = ContextBag()

        async def write_key(key: str, value: str, stage: str):
            await bag.write(key, value, stage)

        # Write to different keys concurrently
        await asyncio.gather(
            write_key("key1", "value1", "stage_a"),
            write_key("key2", "value2", "stage_b"),
            write_key("key3", "value3", "stage_c"),
        )

        assert bag.read("key1") == "value1"
        assert bag.read("key2") == "value2"
        assert bag.read("key3") == "value3"

    @pytest.mark.asyncio
    async def test_concurrent_writes_to_same_key_raises_error(self):
        """Test that concurrent writes to same key raise DataConflictError."""
        bag = ContextBag()

        async def write_key(key: str, value: str, stage: str):
            await asyncio.sleep(0.001)  # Small delay to ensure concurrency
            await bag.write(key, value, stage)

        # One should succeed, one should fail
        with pytest.raises(DataConflictError):
            await asyncio.gather(
                write_key("same_key", "value1", "stage_a"),
                write_key("same_key", "value2", "stage_b"),
            )

    @pytest.mark.asyncio
    async def test_has_returns_true_for_existing_key(self):
        """Test that has() returns True for existing key."""
        bag = ContextBag()
        await bag.write("exists", "value", "stage")

        assert bag.has("exists") is True
        assert bag.has("missing") is False

    @pytest.mark.asyncio
    async def test_keys_returns_all_keys(self):
        """Test that keys() returns all stored keys."""
        bag = ContextBag()
        await bag.write("key1", "value1", "stage_a")
        await bag.write("key2", "value2", "stage_b")

        keys = bag.keys()
        assert set(keys) == {"key1", "key2"}

    @pytest.mark.asyncio
    async def test_get_writer_returns_stage_name(self):
        """Test that get_writer() returns correct stage name."""
        bag = ContextBag()
        await bag.write("key1", "value1", "writer_stage")

        assert bag.get_writer("key1") == "writer_stage"
        assert bag.get_writer("missing") is None

    @pytest.mark.asyncio
    async def test_to_dict_returns_copy(self):
        """Test that to_dict() returns a copy of internal data."""
        bag = ContextBag()
        await bag.write("key1", "value1", "stage")

        data = bag.to_dict()
        assert data == {"key1": "value1"}

        # Modifying copy should not affect bag
        data["key2"] = "value2"
        assert bag.has("key2") is False

    @pytest.mark.asyncio
    async def test_repr(self):
        """Test __repr__ provides useful debugging info."""
        bag = ContextBag()
        await bag.write("key1", "value1", "stage")

        repr_str = repr(bag)
        assert "ContextBag" in repr_str
        assert "key1" in repr_str

    @pytest.mark.asyncio
    async def test_write_various_types(self):
        """Test that write() handles various value types."""
        bag = ContextBag()

        await bag.write("string", "hello", "stage")
        await bag.write("int", 42, "stage")
        await bag.write("list", [1, 2, 3], "stage")
        await bag.write("dict", {"nested": "value"}, "stage")
        await bag.write("none", None, "stage")

        assert bag.read("string") == "hello"
        assert bag.read("int") == 42
        assert bag.read("list") == [1, 2, 3]
        assert bag.read("dict") == {"nested": "value"}
        assert bag.read("none") is None
