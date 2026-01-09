"""Pytest configuration for benchmark tests."""

import pytest


def pytest_configure(config):
    """Configure benchmark markers."""
    config.addinivalue_line(
        "markers", "benchmark: mark test as a benchmark"
    )


@pytest.fixture
def benchmark_context():
    """Create a context suitable for benchmarking."""
    from uuid import uuid4
    from stageflow import PipelineContext
    from tests.utils.mocks import MockEventSink

    return PipelineContext(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=uuid4(),
        interaction_id=uuid4(),
        topology="benchmark",
        execution_mode="benchmark",
        service="benchmark",
        event_sink=MockEventSink(),
    )
