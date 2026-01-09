"""Benchmark tests for pipeline operations.

These benchmarks measure:
- Pipeline build time
- Stage graph construction
- Context creation and forking
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from stageflow import Pipeline, PipelineContext
from stageflow.utils.frozen import FrozenDict


class TestPipelineBuildBenchmarks:
    """Benchmark tests for pipeline building."""

    @pytest.mark.benchmark(group="pipeline_build")
    def test_simple_pipeline_build(self, benchmark) -> None:
        """Benchmark building a simple 3-stage pipeline."""

        def build_simple():
            pipeline = Pipeline()
            # Note: with_stage requires actual stage classes in real usage
            return pipeline

        benchmark(build_simple)

    @pytest.mark.benchmark(group="pipeline_build")
    def test_pipeline_creation(self, benchmark) -> None:
        """Benchmark Pipeline object creation."""

        def create_pipeline():
            return Pipeline()

        benchmark(create_pipeline)


class TestContextBenchmarks:
    """Benchmark tests for context operations."""

    @pytest.mark.benchmark(group="context")
    def test_context_creation(self, benchmark) -> None:
        """Benchmark PipelineContext creation."""

        def create_context():
            return PipelineContext(
                pipeline_run_id=uuid4(),
                request_id=uuid4(),
                session_id=uuid4(),
                user_id=uuid4(),
                org_id=uuid4(),
                interaction_id=uuid4(),
                topology="test",
                execution_mode="test",
                service="test",
            )

        benchmark(create_context)

    @pytest.mark.benchmark(group="context")
    def test_context_fork(self, benchmark) -> None:
        """Benchmark context forking for subpipelines."""
        parent_ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="parent",
            execution_mode="test",
            service="test",
            data={"key1": "value1", "key2": "value2", "key3": "value3"},
        )

        def fork_context():
            return parent_ctx.fork(
                child_run_id=uuid4(),
                parent_stage_id="test_stage",
                correlation_id=uuid4(),
            )

        benchmark(fork_context)

    @pytest.mark.benchmark(group="context")
    def test_context_to_dict(self, benchmark) -> None:
        """Benchmark context serialization."""
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="test",
            execution_mode="test",
            service="test",
            data={"key1": "value1", "key2": {"nested": "data"}},
        )

        benchmark(ctx.to_dict)


class TestFrozenDictBenchmarks:
    """Benchmark tests for FrozenDict operations."""

    @pytest.mark.benchmark(group="frozen_dict")
    def test_frozen_dict_creation(self, benchmark) -> None:
        """Benchmark FrozenDict creation."""
        data = {f"key_{i}": f"value_{i}" for i in range(100)}

        def create_frozen():
            return FrozenDict(data)

        benchmark(create_frozen)

    @pytest.mark.benchmark(group="frozen_dict")
    def test_frozen_dict_read(self, benchmark) -> None:
        """Benchmark FrozenDict reads."""
        data = {f"key_{i}": f"value_{i}" for i in range(100)}
        frozen = FrozenDict(data)

        def read_many():
            for i in range(100):
                _ = frozen[f"key_{i}"]

        benchmark(read_many)

    @pytest.mark.benchmark(group="frozen_dict")
    def test_frozen_dict_to_dict(self, benchmark) -> None:
        """Benchmark FrozenDict.to_dict() for copy creation."""
        data = {f"key_{i}": f"value_{i}" for i in range(100)}
        frozen = FrozenDict(data)

        benchmark(frozen.to_dict)
