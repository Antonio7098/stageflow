"""Pytest configuration and fixtures for stageflow tests."""

import asyncio
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest


def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async (requires pytest-asyncio)"
    )


# Add the source directory to the path
tests_dir = Path(__file__).parent
stageflow_dir = tests_dir.parent
if str(stageflow_dir) not in sys.path:
    sys.path.insert(0, str(stageflow_dir))


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def anyio_backend():
    """Set anyio backend for async tests."""
    return "asyncio"


# === Common Fixtures ===

@pytest.fixture
def sample_uuid():
    """Return a sample UUID."""
    return uuid4()


@pytest.fixture
def sample_pipeline_run_id():
    """Return a sample pipeline run ID."""
    return uuid4()


@pytest.fixture
def sample_request_id():
    """Return a sample request ID."""
    return uuid4()


@pytest.fixture
def sample_session_id():
    """Return a sample session ID."""
    return uuid4()


@pytest.fixture
def sample_user_id():
    """Return a sample user ID."""
    return uuid4()


@pytest.fixture
def sample_org_id():
    """Return a sample org ID."""
    return uuid4()


@pytest.fixture
def sample_interaction_id():
    """Return a sample interaction ID."""
    return uuid4()


@pytest.fixture
def sample_topology():
    """Return a sample topology."""
    return "chat_fast"


@pytest.fixture
def sample_execution_mode():
    """Return a sample execution mode."""
    return "practice"


# === Stage Fixtures ===

@pytest.fixture
def simple_stage_result():
    """Return a simple stage result dict."""
    return {"status": "completed", "data": {"result": "success"}}


@pytest.fixture
def failed_stage_result():
    """Return a failed stage result dict."""
    return {"status": "failed", "error": "Stage failed"}


# === Data Fixtures ===

@pytest.fixture
def sample_context_data():
    """Return sample context data."""
    return {
        "key": "value",
        "number": 42,
        "nested": {"a": {"b": "c"}},
    }


@pytest.fixture
def sample_stage_data():
    """Return sample stage data."""
    return {
        "transcript": "Hello, world!",
        "confidence": 0.95,
        "duration_ms": 1500,
    }


@pytest.fixture
def sample_context():
    """Create a minimal PipelineContext for testing."""
    from stageflow import PipelineContext

    return PipelineContext(
        pipeline_run_id=None,
        request_id=None,
        session_id=None,
        user_id=None,
        org_id=None,
        interaction_id=None,
        topology="test_topology",
        execution_mode="test",
        service="test",
    )
