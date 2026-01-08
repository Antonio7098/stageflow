"""Pytest configuration for stageflow tests."""

import pytest


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
        behavior="test",
        service="test",
    )
