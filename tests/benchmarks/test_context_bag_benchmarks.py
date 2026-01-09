"""Benchmark tests for ContextBag throughput.

These benchmarks measure:
- Sequential write throughput
- Read throughput
- Concurrent write performance
"""

from __future__ import annotations

import asyncio

import pytest

from stageflow.context.bag import ContextBag


class TestContextBagBenchmarks:
    """Benchmark tests for ContextBag operations."""

    @pytest.mark.benchmark(group="context_bag")
    def test_sequential_writes_throughput(self, benchmark) -> None:
        """Benchmark sequential write operations."""

        async def write_many():
            bag = ContextBag()
            for i in range(1000):
                await bag.write(f"key_{i}", f"value_{i}", f"stage_{i}")
            return bag

        def run():
            return asyncio.get_event_loop().run_until_complete(write_many())

        result = benchmark(run)
        assert len(result.keys()) == 1000

    @pytest.mark.benchmark(group="context_bag")
    def test_read_throughput(self, benchmark) -> None:
        """Benchmark read operations."""

        async def setup():
            bag = ContextBag()
            for i in range(1000):
                await bag.write(f"key_{i}", f"value_{i}", f"stage_{i}")
            return bag

        bag = asyncio.get_event_loop().run_until_complete(setup())

        def read_many():
            for i in range(1000):
                bag.read(f"key_{i}")

        benchmark(read_many)

    @pytest.mark.benchmark(group="context_bag")
    def test_has_check_throughput(self, benchmark) -> None:
        """Benchmark has() check operations."""

        async def setup():
            bag = ContextBag()
            for i in range(500):
                await bag.write(f"key_{i}", f"value_{i}", f"stage_{i}")
            return bag

        bag = asyncio.get_event_loop().run_until_complete(setup())

        def check_many():
            for i in range(1000):
                bag.has(f"key_{i}")

        benchmark(check_many)

    @pytest.mark.benchmark(group="context_bag")
    def test_to_dict_throughput(self, benchmark) -> None:
        """Benchmark to_dict() operations."""

        async def setup():
            bag = ContextBag()
            for i in range(100):
                await bag.write(f"key_{i}", f"value_{i}", f"stage_{i}")
            return bag

        bag = asyncio.get_event_loop().run_until_complete(setup())

        def to_dict_many():
            for _ in range(100):
                bag.to_dict()

        benchmark(to_dict_many)


class TestContextBagConcurrency:
    """Benchmark tests for concurrent ContextBag operations."""

    @pytest.mark.benchmark(group="context_bag_concurrent")
    def test_concurrent_writes_different_keys(self, benchmark) -> None:
        """Benchmark concurrent writes to different keys."""

        async def concurrent_writes():
            bag = ContextBag()

            async def write_batch(start: int):
                for i in range(100):
                    await bag.write(f"key_{start}_{i}", f"value_{i}", f"stage_{start}")

            tasks = [write_batch(i) for i in range(10)]
            await asyncio.gather(*tasks)
            return bag

        def run():
            return asyncio.get_event_loop().run_until_complete(concurrent_writes())

        result = benchmark(run)
        assert len(result.keys()) == 1000
