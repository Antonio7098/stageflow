"""Tests for ToolExecutor.spawn_subpipeline method."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from stageflow.core import StageKind, StageOutput
from stageflow.events import NoOpEventSink
from stageflow.pipeline import (
    MaxDepthExceededError,
    Pipeline,
    PipelineRegistry,
    SubpipelineResult,
    SubpipelineSpawner,
)
from stageflow.stages.context import PipelineContext
from stageflow.tools.executor import ToolExecutor, ToolExecutorResult


def create_test_pipeline_context(
    *,
    pipeline_run_id: UUID | None = None,
    request_id: UUID | None = None,
    session_id: UUID | None = None,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
    interaction_id: UUID | None = None,
    topology: str | None = "test",
    execution_mode: str | None = "practice",
) -> PipelineContext:
    """Create a PipelineContext for testing."""
    return PipelineContext(
        pipeline_run_id=pipeline_run_id or uuid4(),
        request_id=request_id or uuid4(),
        session_id=session_id or uuid4(),
        user_id=user_id or uuid4(),
        org_id=org_id,
        interaction_id=interaction_id or uuid4(),
        topology=topology,
        execution_mode=execution_mode,
        event_sink=NoOpEventSink(),
    )


class MockStage:
    """Mock stage for testing pipelines."""

    id = "mock_stage"

    async def execute(self, _ctx: Any) -> StageOutput:
        return StageOutput.ok(data={"mock": "data"})


class TestToolExecutorInit:
    """Test ToolExecutor initialization."""

    def test_default_init(self):
        """Should initialize with default global instances."""
        executor = ToolExecutor()
        assert executor._spawner is None
        assert executor._pipeline_registry is None
        assert executor.tool_registry is not None

    def test_init_with_injected_dependencies(self):
        """Should accept injected spawner and registry."""
        mock_spawner = MagicMock(spec=SubpipelineSpawner)
        mock_registry = MagicMock(spec=PipelineRegistry)

        executor = ToolExecutor(spawner=mock_spawner, registry=mock_registry)

        assert executor._spawner is mock_spawner
        assert executor._pipeline_registry is mock_registry

    def test_lazy_spawner_initialization(self):
        """Should lazily initialize spawner on first access."""
        executor = ToolExecutor()
        assert executor._spawner is None

        # Access spawner property
        spawner = executor.spawner
        assert spawner is not None
        assert executor._spawner is spawner

    def test_lazy_registry_initialization(self):
        """Should lazily initialize registry on first access."""
        executor = ToolExecutor()
        assert executor._pipeline_registry is None

        # Access registry property
        registry = executor.pipeline_registry
        assert registry is not None
        assert executor._pipeline_registry is registry


class TestToolExecutorResult:
    """Test ToolExecutorResult dataclass."""

    def test_default_values(self):
        """Should have correct default values."""
        result = ToolExecutorResult()
        assert result.actions_executed == 0
        assert result.actions_failed == 0
        assert result.artifacts_produced == []
        assert result.requires_reentry is False
        assert result.error is None
        assert result.subpipeline_runs == []

    def test_subpipeline_runs_field(self):
        """Should store subpipeline run results."""
        result = ToolExecutorResult(
            subpipeline_runs=[
                {"success": True, "child_run_id": str(uuid4()), "duration_ms": 100.0}
            ]
        )
        assert len(result.subpipeline_runs) == 1
        assert result.subpipeline_runs[0]["success"] is True


class TestSpawnSubpipeline:
    """Test ToolExecutor.spawn_subpipeline method."""

    @pytest.fixture
    def mock_spawner(self):
        """Create a mock SubpipelineSpawner."""
        spawner = MagicMock(spec=SubpipelineSpawner)
        spawner.spawn = AsyncMock()
        return spawner

    @pytest.fixture
    def mock_registry(self):
        """Create a mock PipelineRegistry."""
        registry = MagicMock(spec=PipelineRegistry)
        return registry

    @pytest.fixture
    def mock_pipeline(self):
        """Create a mock Pipeline."""
        pipeline = MagicMock(spec=Pipeline)
        mock_graph = MagicMock()
        mock_graph.run = AsyncMock(return_value={
            "stage1": StageOutput.ok(data={"result": "value"})
        })
        pipeline.build.return_value = mock_graph
        return pipeline

    @pytest.fixture
    def executor(self, mock_spawner, mock_registry):
        """Create ToolExecutor with mocked dependencies."""
        return ToolExecutor(spawner=mock_spawner, registry=mock_registry)

    @pytest.fixture
    def ctx(self):
        """Create a test PipelineContext."""
        return create_test_pipeline_context()

    @pytest.mark.asyncio
    async def test_happy_path_spawns_subpipeline(
        self, executor, mock_spawner, mock_registry, mock_pipeline, ctx
    ):
        """Should spawn subpipeline and return result."""
        correlation_id = uuid4()
        child_run_id = uuid4()

        mock_registry.get.return_value = mock_pipeline
        mock_spawner.spawn.return_value = SubpipelineResult(
            success=True,
            child_run_id=child_run_id,
            data={"stage1": {"result": "value"}},
            duration_ms=50.0,
        )

        result = await executor.spawn_subpipeline(
            "test_pipeline",
            ctx,
            correlation_id,
        )

        assert result.success is True
        assert result.child_run_id == child_run_id
        assert result.data == {"stage1": {"result": "value"}}
        assert result.duration_ms == 50.0

        # Verify spawner was called with correct arguments
        mock_spawner.spawn.assert_called_once()
        call_kwargs = mock_spawner.spawn.call_args.kwargs
        assert call_kwargs["pipeline_name"] == "test_pipeline"
        assert call_kwargs["ctx"] is ctx
        assert call_kwargs["correlation_id"] == correlation_id
        assert call_kwargs["parent_stage_id"] == "stage.tool_executor"

    @pytest.mark.asyncio
    async def test_pipeline_not_found_raises_keyerror(
        self, executor, mock_registry, ctx
    ):
        """Should raise KeyError when pipeline not found."""
        mock_registry.get.side_effect = KeyError("Pipeline 'missing' not found")

        with pytest.raises(KeyError) as exc_info:
            await executor.spawn_subpipeline(
                "missing",
                ctx,
                uuid4(),
            )

        assert "missing" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_max_depth_exceeded_raises(
        self, executor, mock_spawner, mock_registry, mock_pipeline, ctx
    ):
        """Should raise MaxDepthExceededError when depth limit exceeded."""
        mock_registry.get.return_value = mock_pipeline
        mock_spawner.spawn.side_effect = MaxDepthExceededError(
            current_depth=5,
            max_depth=5,
            parent_run_id=ctx.pipeline_run_id,
        )

        with pytest.raises(MaxDepthExceededError) as exc_info:
            await executor.spawn_subpipeline(
                "test_pipeline",
                ctx,
                uuid4(),
            )

        assert exc_info.value.current_depth == 5
        assert exc_info.value.max_depth == 5

    @pytest.mark.asyncio
    async def test_topology_override_passed_to_spawner(
        self, executor, mock_spawner, mock_registry, mock_pipeline, ctx
    ):
        """Should pass topology_override to spawner."""
        mock_registry.get.return_value = mock_pipeline
        mock_spawner.spawn.return_value = SubpipelineResult(
            success=True,
            child_run_id=uuid4(),
            data={},
            duration_ms=10.0,
        )

        await executor.spawn_subpipeline(
            "test_pipeline",
            ctx,
            uuid4(),
            topology_override="fast_kernel",
        )

        call_kwargs = mock_spawner.spawn.call_args.kwargs
        assert call_kwargs["topology"] == "fast_kernel"

    @pytest.mark.asyncio
    async def test_execution_mode_override_passed_to_spawner(
        self, executor, mock_spawner, mock_registry, mock_pipeline, ctx
    ):
        """Should pass execution_mode_override to spawner."""
        mock_registry.get.return_value = mock_pipeline
        mock_spawner.spawn.return_value = SubpipelineResult(
            success=True,
            child_run_id=uuid4(),
            data={},
            duration_ms=10.0,
        )

        await executor.spawn_subpipeline(
            "test_pipeline",
            ctx,
            uuid4(),
            execution_mode_override="strict",
        )

        call_kwargs = mock_spawner.spawn.call_args.kwargs
        assert call_kwargs["execution_mode"] == "strict"

    @pytest.mark.asyncio
    async def test_failed_subpipeline_returns_error_result(
        self, executor, mock_spawner, mock_registry, mock_pipeline, ctx
    ):
        """Should return SubpipelineResult with error on failure."""
        mock_registry.get.return_value = mock_pipeline
        mock_spawner.spawn.return_value = SubpipelineResult(
            success=False,
            child_run_id=uuid4(),
            error="Stage execution failed",
            duration_ms=25.0,
        )

        result = await executor.spawn_subpipeline(
            "test_pipeline",
            ctx,
            uuid4(),
        )

        assert result.success is False
        assert result.error == "Stage execution failed"

    @pytest.mark.asyncio
    async def test_spawner_exception_propagates(
        self, executor, mock_spawner, mock_registry, mock_pipeline, ctx
    ):
        """Should propagate unexpected exceptions from spawner."""
        mock_registry.get.return_value = mock_pipeline
        mock_spawner.spawn.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(RuntimeError) as exc_info:
            await executor.spawn_subpipeline(
                "test_pipeline",
                ctx,
                uuid4(),
            )

        assert "Unexpected error" in str(exc_info.value)


class TestSpawnSubpipelineRunner:
    """Test the runner callable created by spawn_subpipeline."""

    @pytest.fixture
    def real_pipeline(self):
        """Create a real Pipeline with a mock stage."""
        return Pipeline().with_stage("mock", MockStage, StageKind.TRANSFORM)

    @pytest.fixture
    def mock_spawner(self):
        """Create a mock spawner that captures the runner."""
        spawner = MagicMock(spec=SubpipelineSpawner)
        spawner.spawn = AsyncMock()
        return spawner

    @pytest.fixture
    def mock_registry(self, real_pipeline):
        """Create a mock registry returning the real pipeline."""
        registry = MagicMock(spec=PipelineRegistry)
        registry.get.return_value = real_pipeline
        return registry

    @pytest.mark.asyncio
    async def test_runner_executes_pipeline_graph(
        self, mock_spawner, mock_registry
    ):
        """Should create a runner that executes the pipeline graph."""
        executor = ToolExecutor(spawner=mock_spawner, registry=mock_registry)
        ctx = create_test_pipeline_context()
        correlation_id = uuid4()

        # Configure spawner to capture and execute the runner
        captured_runner = None

        async def capture_runner(**kwargs):
            nonlocal captured_runner
            captured_runner = kwargs["runner"]
            # Create a child context for the runner
            child_ctx = ctx.fork(
                child_run_id=uuid4(),
                parent_stage_id="stage.tool_executor",
                correlation_id=correlation_id,
            )
            # Execute the runner
            result = await captured_runner(child_ctx)
            return SubpipelineResult(
                success=True,
                child_run_id=child_ctx.pipeline_run_id,
                data=result,
                duration_ms=10.0,
            )

        mock_spawner.spawn.side_effect = capture_runner

        result = await executor.spawn_subpipeline(
            "test_pipeline",
            ctx,
            correlation_id,
        )

        assert captured_runner is not None
        assert result.success is True
        # The runner should have executed and returned stage outputs
        assert result.data is not None


class TestSpawnSubpipelineObservability:
    """Test observability features of spawn_subpipeline."""

    @pytest.fixture
    def mock_spawner(self):
        """Create a mock SubpipelineSpawner."""
        spawner = MagicMock(spec=SubpipelineSpawner)
        spawner.spawn = AsyncMock()
        return spawner

    @pytest.fixture
    def mock_registry(self):
        """Create a mock PipelineRegistry."""
        registry = MagicMock(spec=PipelineRegistry)
        mock_pipeline = MagicMock(spec=Pipeline)
        mock_graph = MagicMock()
        mock_graph.run = AsyncMock(return_value={})
        mock_pipeline.build.return_value = mock_graph
        registry.get.return_value = mock_pipeline
        return registry

    @pytest.mark.asyncio
    async def test_logs_spawn_start(
        self, mock_spawner, mock_registry, caplog
    ):
        """Should log when spawning starts."""
        executor = ToolExecutor(spawner=mock_spawner, registry=mock_registry)
        ctx = create_test_pipeline_context()

        mock_spawner.spawn.return_value = SubpipelineResult(
            success=True,
            child_run_id=uuid4(),
            data={},
            duration_ms=10.0,
        )

        with caplog.at_level("INFO", logger="stageflow.tools.executor"):
            await executor.spawn_subpipeline(
                "test_pipeline",
                ctx,
                uuid4(),
            )

        assert any("Spawning subpipeline" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_spawn_completion(
        self, mock_spawner, mock_registry, caplog
    ):
        """Should log when spawning completes."""
        executor = ToolExecutor(spawner=mock_spawner, registry=mock_registry)
        ctx = create_test_pipeline_context()

        mock_spawner.spawn.return_value = SubpipelineResult(
            success=True,
            child_run_id=uuid4(),
            data={},
            duration_ms=10.0,
        )

        with caplog.at_level("INFO", logger="stageflow.tools.executor"):
            await executor.spawn_subpipeline(
                "test_pipeline",
                ctx,
                uuid4(),
            )

        assert any("Subpipeline completed" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_pipeline_not_found_error(
        self, mock_spawner, mock_registry, caplog
    ):
        """Should log error when pipeline not found."""
        executor = ToolExecutor(spawner=mock_spawner, registry=mock_registry)
        ctx = create_test_pipeline_context()

        mock_registry.get.side_effect = KeyError("Pipeline 'missing' not found")

        with caplog.at_level("ERROR", logger="stageflow.tools.executor"), pytest.raises(KeyError):
            await executor.spawn_subpipeline(
                "missing",
                ctx,
                uuid4(),
            )

        assert any("not found in registry" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_max_depth_exceeded(
        self, mock_spawner, mock_registry, caplog
    ):
        """Should log error when max depth exceeded."""
        executor = ToolExecutor(spawner=mock_spawner, registry=mock_registry)
        ctx = create_test_pipeline_context()

        mock_spawner.spawn.side_effect = MaxDepthExceededError(
            current_depth=5,
            max_depth=5,
            parent_run_id=ctx.pipeline_run_id,
        )

        with caplog.at_level("ERROR", logger="stageflow.tools.executor"), pytest.raises(MaxDepthExceededError):
            await executor.spawn_subpipeline(
                "test_pipeline",
                ctx,
                uuid4(),
            )

        assert any("max depth exceeded" in record.message for record in caplog.records)
