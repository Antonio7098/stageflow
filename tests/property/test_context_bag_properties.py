"""Property-based tests for ContextBag conflict detection.

These tests verify that:
- Writing same key twice always raises DataConflictError
- Writing different keys never raises
- Read after write always returns written value
"""

from __future__ import annotations

import asyncio

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from stageflow.context.bag import ContextBag, DataConflictError
from tests.property.strategies import context_keys, context_values


class TestContextBagProperties:
    """Property tests for ContextBag."""

    @given(context_keys(), context_values())
    @settings(max_examples=100)
    def test_write_then_read_returns_value(self, key: str, value) -> None:
        """Reading after writing always returns the written value."""
        bag = ContextBag()

        async def test():
            await bag.write(key, value, "test_stage")
            result = bag.read(key)
            assert result == value, f"Expected {value}, got {result}"

        asyncio.get_event_loop().run_until_complete(test())

    @given(context_keys(), context_values(), context_values())
    @settings(max_examples=100)
    def test_double_write_same_key_raises(self, key: str, value1, value2) -> None:
        """Writing the same key twice always raises DataConflictError."""
        bag = ContextBag()

        async def test():
            await bag.write(key, value1, "stage_a")
            with pytest.raises(DataConflictError) as exc_info:
                await bag.write(key, value2, "stage_b")

            assert exc_info.value.key == key
            assert exc_info.value.existing_writer == "stage_a"
            assert exc_info.value.new_writer == "stage_b"

        asyncio.get_event_loop().run_until_complete(test())

    @given(
        st.lists(context_keys(), min_size=2, max_size=10, unique=True),
        st.lists(context_values(), min_size=2, max_size=10),
    )
    @settings(max_examples=50)
    def test_different_keys_never_conflict(self, keys: list[str], values: list) -> None:
        """Writing different keys never raises."""
        bag = ContextBag()

        async def test():
            for i, key in enumerate(keys):
                value = values[i % len(values)]
                await bag.write(key, value, f"stage_{i}")

            # All keys should be readable
            for i, key in enumerate(keys):
                expected = values[i % len(values)]
                assert bag.read(key) == expected

        asyncio.get_event_loop().run_until_complete(test())

    @given(context_keys())
    @settings(max_examples=50)
    def test_read_missing_key_returns_default(self, key: str) -> None:
        """Reading a missing key returns the default value."""
        bag = ContextBag()
        assert bag.read(key) is None
        assert bag.read(key, "default") == "default"

    @given(context_keys(), context_values())
    @settings(max_examples=50)
    def test_has_returns_true_after_write(self, key: str, value) -> None:
        """has() returns True after writing a key."""
        bag = ContextBag()

        async def test():
            assert not bag.has(key)
            await bag.write(key, value, "test_stage")
            assert bag.has(key)

        asyncio.get_event_loop().run_until_complete(test())

    @given(context_keys(), context_values())
    @settings(max_examples=50)
    def test_get_writer_returns_stage_name(self, key: str, value) -> None:
        """get_writer() returns the stage that wrote the key."""
        bag = ContextBag()
        stage_name = "my_stage"

        async def test():
            assert bag.get_writer(key) is None
            await bag.write(key, value, stage_name)
            assert bag.get_writer(key) == stage_name

        asyncio.get_event_loop().run_until_complete(test())

    @given(
        st.lists(context_keys(), min_size=1, max_size=5, unique=True),
        context_values(),
    )
    @settings(max_examples=50)
    def test_to_dict_contains_all_written_keys(self, keys: list[str], value) -> None:
        """to_dict() contains all written keys."""
        bag = ContextBag()

        async def test():
            for i, key in enumerate(keys):
                await bag.write(key, value, f"stage_{i}")

            result = bag.to_dict()
            for key in keys:
                assert key in result
                assert result[key] == value

        asyncio.get_event_loop().run_until_complete(test())
