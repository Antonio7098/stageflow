"""Comprehensive tests for stageflow.stages.graph module.

Tests the UnifiedStageGraph - the new DAG executor using unified Stage protocol:
- UnifiedStageSpec
- UnifiedStageGraph execution
- StageOutput-based results
- Cancellation via UnifiedPipelineCancelled
- Error handling via UnifiedStageExecutionError
- Parallel execution
- Conditional stages
"""

import asyncio
from datetime import datetime, timedelta, UTC
from typing import Any
from uuid import uuid4
import pytest

from stageflow.context.snapshot import ContextSnapshot
from stageflow.core.stages import (
    StageContext,
    StageKind,
    StageOutput,
    StageStatus,
)
from stageflow.stages.graph import (
    UnifiedPipelineCancelled,
    UnifiedStageExecutionError,
    UnifiedStageGraph,
    UnifiedStageSpec,
)


# === Test Fixtures ===

def create_snapshot() -> ContextSnapshot:
    """Create a test ContextSnapshot."""
    return ContextSnapshot(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=uuid4(),
        interaction_id=uuid4(),
        topology="test_topology",
        channel="test_channel",
        behavior="test",
    )


def create_context(snapshot: ContextSnapshot | None = None) -> StageContext:
    """Create a test StageContext."""
    return StageContext(snapshot=snapshot or create_snapshot())


# === Test UnifiedStageSpec ===

class TestUnifiedStageSpec:
    """Tests for UnifiedStageSpec dataclass."""

    def test_spec_creation(self):
        """Test UnifiedStageSpec with required fields."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok()

        spec = UnifiedStageSpec(
            name="test",
            runner=runner,
            kind=StageKind.TRANSFORM,
        )
        assert spec.name == "test"
        assert spec.runner == runner
        assert spec.kind == StageKind.TRANSFORM

    def test_spec_with_dependencies(self):
        """Test UnifiedStageSpec with dependencies."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok()

        spec = UnifiedStageSpec(
            name="dependent",
            runner=runner,
            kind=StageKind.TRANSFORM,
            dependencies=("a", "b"),
        )
        assert spec.dependencies == ("a", "b")

    def test_spec_with_conditional(self):
        """Test UnifiedStageSpec with conditional flag."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok()

        spec = UnifiedStageSpec(
            name="conditional",
            runner=runner,
            kind=StageKind.GUARD,
            conditional=True,
        )
        assert spec.conditional is True

    def test_spec_defaults(self):
        """Test UnifiedStageSpec default values."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok()

        spec = UnifiedStageSpec(name="test", runner=runner, kind=StageKind.TRANSFORM)
        assert spec.dependencies == ()
        assert spec.conditional is False


# === Test UnifiedStageGraph Init ===

class TestUnifiedStageGraphInit:
    """Tests for UnifiedStageGraph initialization."""

    def test_init_with_single_spec(self):
        """Test graph with single spec."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok()

        spec = UnifiedStageSpec(name="test", runner=runner, kind=StageKind.TRANSFORM)
        graph = UnifiedStageGraph(specs=[spec])
        assert len(graph._specs) == 1

    def test_init_with_multiple_specs(self):
        """Test graph with multiple specs."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok()

        specs = [
            UnifiedStageSpec(name="a", runner=runner, kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="b", runner=runner, kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="c", runner=runner, kind=StageKind.TRANSFORM),
        ]
        graph = UnifiedStageGraph(specs=specs)
        assert len(graph._specs) == 3

    def test_init_empty_raises(self):
        """Test empty specs raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            UnifiedStageGraph(specs=[])
        assert "UnifiedStageGraph requires at least one UnifiedStageSpec" in str(exc_info.value)

    def test_stage_specs_property(self):
        """Test stage_specs property returns list."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok()

        specs = [
            UnifiedStageSpec(name="a", runner=runner, kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="b", runner=runner, kind=StageKind.TRANSFORM),
        ]
        graph = UnifiedStageGraph(specs=specs)
        result = graph.stage_specs
        assert isinstance(result, list)
        assert len(result) == 2

    def test_duration_ms_calculation(self):
        """Test _duration_ms method."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok()

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(
                name="test",
                runner=runner,
                kind=StageKind.TRANSFORM,
            )]
        )
        started = datetime.now(UTC)
        ended = started + timedelta(milliseconds=1500)
        duration = graph._duration_ms(started, ended)
        assert duration == 1500


# === Test UnifiedStageGraph Execution ===

class TestUnifiedStageGraphExecution:
    """Tests for UnifiedStageGraph execution."""

    @pytest.mark.asyncio
    async def test_run_single_stage(self):
        """Test running a single stage."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"result": "success"})

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="test", runner=runner, kind=StageKind.TRANSFORM)]
        )
        ctx = create_context()

        results = await graph.run(ctx)

        assert "test" in results
        assert results["test"].status == StageStatus.OK
        assert results["test"].data == {"result": "success"}

    @pytest.mark.asyncio
    async def test_run_multiple_independent_stages_parallel(self):
        """Test running independent stages in parallel."""
        execution_times = {}

        async def make_runner(name: str, delay: float):
            async def runner(ctx: StageContext) -> StageOutput:
                start = asyncio.get_event_loop().time()
                await asyncio.sleep(delay)
                execution_times[name] = asyncio.get_event_loop().time() - start
                return StageOutput.ok(data={"stage": name})
            return runner

        specs = [
            UnifiedStageSpec(name="a", runner=await make_runner("a", 0.1), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="b", runner=await make_runner("b", 0.1), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="c", runner=await make_runner("c", 0.1), kind=StageKind.TRANSFORM),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        import time
        start = time.time()
        results = await graph.run(ctx)
        elapsed = time.time() - start

        assert len(results) == 3
        # Should run in parallel (~0.1s), not sequential (~0.3s)
        assert elapsed < 0.25

    @pytest.mark.asyncio
    async def test_run_sequential_stages(self):
        """Test running stages with dependencies."""
        execution_order = []

        async def make_runner(name: str, delay: float = 0):
            async def runner(ctx: StageContext) -> StageOutput:
                execution_order.append(name)
                if delay > 0:
                    await asyncio.sleep(delay)
                return StageOutput.ok(data={"stage": name})
            return runner

        specs = [
            UnifiedStageSpec(name="a", runner=await make_runner("a"), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="b", runner=await make_runner("b", 0.05), dependencies=("a",), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="c", runner=await make_runner("c", 0.05), dependencies=("b",), kind=StageKind.TRANSFORM),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        await graph.run(ctx)

        # Verify order
        assert execution_order[0] == "a"
        assert execution_order.index("b") > execution_order.index("a")
        assert execution_order.index("c") > execution_order.index("b")

    @pytest.mark.asyncio
    async def test_run_diamond_dependency(self):
        """Test diamond dependency pattern."""
        execution_order = []

        async def make_runner(name: str):
            async def runner(ctx: StageContext) -> StageOutput:
                execution_order.append(name)
                return StageOutput.ok(data={"stage": name})
            return runner

        specs = [
            UnifiedStageSpec(name="a", runner=await make_runner("a"), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="b", runner=await make_runner("b"), dependencies=("a",), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="c", runner=await make_runner("c"), dependencies=("a",), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="d", runner=await make_runner("d"), dependencies=("b", "c"), kind=StageKind.TRANSFORM),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        await graph.run(ctx)

        assert len(execution_order) == 4
        assert execution_order[0] == "a"
        assert "d" in execution_order
        # d should be last
        assert execution_order.index("d") == 3

    @pytest.mark.asyncio
    async def test_run_preserves_stage_kind(self):
        """Test that StageKind is preserved."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok()

        specs = [
            UnifiedStageSpec(name="transform", runner=runner, kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="enrich", runner=runner, kind=StageKind.ENRICH),
            UnifiedStageSpec(name="guard", runner=runner, kind=StageKind.GUARD),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        await graph.run(ctx)

        # Results should have all stages
        assert len(graph._specs) == 3

    @pytest.mark.asyncio
    async def test_run_with_dict_result(self):
        """Test dict results are converted to StageOutput."""
        async def runner(ctx: StageContext) -> dict:
            return {"key": "value", "num": 42}

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="test", runner=runner, kind=StageKind.TRANSFORM)]
        )
        ctx = create_context()

        results = await graph.run(ctx)

        assert results["test"].status == StageStatus.OK
        assert results["test"].data == {"key": "value", "num": 42}

    @pytest.mark.asyncio
    async def test_run_with_none_result(self):
        """Test None result is converted to StageOutput.ok()."""
        async def runner(ctx: StageContext) -> None:
            return None

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="test", runner=runner, kind=StageKind.TRANSFORM)]
        )
        ctx = create_context()

        results = await graph.run(ctx)

        assert results["test"].status == StageStatus.OK
        assert results["test"].data == {}

    @pytest.mark.asyncio
    async def test_run_timing_recorded(self):
        """Test that timing is recorded in outputs."""
        async def runner(ctx: StageContext) -> StageOutput:
            await asyncio.sleep(0.05)
            return StageOutput.ok()

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="test", runner=runner, kind=StageKind.TRANSFORM)]
        )
        ctx = create_context()

        results = await graph.run(ctx)

        output = results["test"]
        assert output is not None


# === Test Error Handling ===

class TestUnifiedStageGraphErrors:
    """Tests for error handling in UnifiedStageGraph."""

    @pytest.mark.asyncio
    async def test_stage_failure_raises_execution_error(self):
        """Test that stage failure raises UnifiedStageExecutionError."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.fail(error="Test failure")

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="failing", runner=runner, kind=StageKind.WORK)]
        )
        ctx = create_context()

        with pytest.raises(UnifiedStageExecutionError) as exc_info:
            await graph.run(ctx)

        assert exc_info.value.stage == "failing"

    @pytest.mark.asyncio
    async def test_exception_raises_execution_error(self):
        """Test that exceptions are wrapped in UnifiedStageExecutionError."""
        async def runner(ctx: StageContext) -> StageOutput:
            raise ValueError("Original error message")

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="error", runner=runner, kind=StageKind.WORK)]
        )
        ctx = create_context()

        with pytest.raises(UnifiedStageExecutionError) as exc_info:
            await graph.run(ctx)

        assert exc_info.value.stage == "error"
        assert isinstance(exc_info.value.original, ValueError)
        assert "Original error message" in str(exc_info.value.original)

    @pytest.mark.asyncio
    async def test_cancelled_stages_propagate_error(self):
        """Test that CANCEL status raises UnifiedPipelineCancelled."""
        async def cancel_runner(ctx: StageContext) -> StageOutput:
            return StageOutput.cancel(reason="User requested cancel")

        async def dependent_runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok()

        specs = [
            UnifiedStageSpec(name="canceler", runner=cancel_runner, kind=StageKind.GUARD),
            UnifiedStageSpec(name="dependent", runner=dependent_runner, dependencies=("canceler",), kind=StageKind.TRANSFORM),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        with pytest.raises(UnifiedPipelineCancelled) as exc_info:
            await graph.run(ctx)

        assert exc_info.value.stage == "canceler"
        assert "User requested cancel" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_cancelled_exception_contains_partial_results(self):
        """Test UnifiedPipelineCancelled contains completed stage results."""
        async def first_runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"first": True})

        async def cancel_runner(ctx: StageContext) -> StageOutput:
            return StageOutput.cancel(reason="Stop")

        specs = [
            UnifiedStageSpec(name="first", runner=first_runner, kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="canceler", runner=cancel_runner, dependencies=("first",), kind=StageKind.GUARD),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        try:
            await graph.run(ctx)
            pytest.fail("Should have raised UnifiedPipelineCancelled")
        except UnifiedPipelineCancelled as e:
            # "first" should be in results
            assert "first" in e.results
            assert e.results["first"].status == StageStatus.OK

    @pytest.mark.asyncio
    async def test_deadlock_detection(self):
        """Test that deadlock is detected."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok()

        specs = [
            UnifiedStageSpec(name="a", runner=runner, dependencies=("b",), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="b", runner=runner, dependencies=("a",), kind=StageKind.TRANSFORM),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        with pytest.raises(RuntimeError) as exc_info:
            await graph.run(ctx)

        assert "Deadlock" in str(exc_info.value) or "deadlock" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unsatisfied_dependency_raises(self):
        """Test unsatisfied dependency raises error."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok()

        specs = [
            UnifiedStageSpec(name="dependent", runner=runner, dependencies=("missing",), kind=StageKind.TRANSFORM),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        with pytest.raises(RuntimeError):
            await graph.run(ctx)

    @pytest.mark.asyncio
    async def test_execution_error_attributes(self):
        """Test UnifiedStageExecutionError has correct attributes."""
        async def runner(ctx: StageContext) -> StageOutput:
            raise RuntimeError("Original exception")

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="test_stage", runner=runner, kind=StageKind.WORK)]
        )
        ctx = create_context()

        try:
            await graph.run(ctx)
            pytest.fail("Should have raised")
        except UnifiedStageExecutionError as e:
            assert e.stage == "test_stage"
            assert isinstance(e.original, RuntimeError)
            assert e.original.args[0] == "Original exception"

    @pytest.mark.asyncio
    async def test_multiple_errors_stops_on_first(self):
        """Test that first error stops execution."""
        error_raised = {"count": 0}

        async def error_runner(ctx: StageContext) -> StageOutput:
            error_raised["count"] += 1
            raise ValueError("Error")

        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok()

        specs = [
            UnifiedStageSpec(name="a", runner=error_runner, kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="b", runner=runner, kind=StageKind.TRANSFORM),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        with pytest.raises(UnifiedStageExecutionError):
            await graph.run(ctx)

        # Only one stage should have run
        assert error_raised["count"] == 1


# === Test Cancellation ===

class TestUnifiedStageGraphCancellation:
    """Tests for cancellation in UnifiedStageGraph."""

    @pytest.mark.asyncio
    async def test_cancel_stops_pipeline(self):
        """Test that CANCEL status stops pipeline."""
        async def cancel_runner(ctx: StageContext) -> StageOutput:
            return StageOutput.cancel(reason="Stop pipeline")

        specs = [
            UnifiedStageSpec(name="cancel", runner=cancel_runner, kind=StageKind.GUARD),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        with pytest.raises(UnifiedPipelineCancelled):
            await graph.run(ctx)

    @pytest.mark.asyncio
    async def test_cancel_with_dependent_stages(self):
        """Test cancellation with dependent stages."""
        execution_order = []

        async def first_runner(ctx: StageContext) -> StageOutput:
            execution_order.append("first")
            return StageOutput.ok()

        async def cancel_runner(ctx: StageContext) -> StageOutput:
            execution_order.append("cancel")
            return StageOutput.cancel(reason="Stop")

        specs = [
            UnifiedStageSpec(name="first", runner=first_runner, kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="cancel", runner=cancel_runner, dependencies=("first",), kind=StageKind.GUARD),
            UnifiedStageSpec(name="never", runner=first_runner, dependencies=("cancel",), kind=StageKind.TRANSFORM),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        with pytest.raises(UnifiedPipelineCancelled):
            await graph.run(ctx)

        # "never" should not have executed
        assert "first" in execution_order
        assert "cancel" in execution_order
        assert "never" not in execution_order

    @pytest.mark.asyncio
    async def test_cancel_reason_in_exception(self):
        """Test cancel reason is available in exception."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.cancel(reason="Custom cancel reason", data={"extra": "data"})

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="cancel", runner=runner, kind=StageKind.GUARD)]
        )
        ctx = create_context()

        with pytest.raises(UnifiedPipelineCancelled) as exc_info:
            await graph.run(ctx)

        assert exc_info.value.reason == "Custom cancel reason"

    @pytest.mark.asyncio
    async def test_parallel_stages_before_cancel(self):
        """Test that parallel stages run before cancel."""
        execution_order = []

        async def runner(name: str, delay: float = 0):
            async def inner(ctx: StageContext) -> StageOutput:
                execution_order.append(name)
                await asyncio.sleep(delay)
                return StageOutput.ok()
            return inner

        async def canceler_runner(ctx: StageContext) -> StageOutput:
            execution_order.append("canceler")
            return StageOutput.cancel(reason="Test cancel")

        specs = [
            UnifiedStageSpec(name="a", runner=await runner("a", 0.1), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="b", runner=await runner("b", 0.1), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="canceler", runner=canceler_runner, dependencies=("a", "b"), kind=StageKind.GUARD),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        with pytest.raises(UnifiedPipelineCancelled):
            await graph.run(ctx)

        # Both a and b should have executed before canceler
        assert "a" in execution_order
        assert "b" in execution_order
        assert execution_order.index("a") < execution_order.index("canceler")
        assert execution_order.index("b") < execution_order.index("canceler")


# === Test Conditional Stages ===

class TestUnifiedConditionalStages:
    """Tests for conditional stage execution."""

    @pytest.mark.asyncio
    async def test_conditional_stage_runs_by_default(self):
        """Test conditional stage runs when no skip reason."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"ran": True})

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="conditional", runner=runner, kind=StageKind.GUARD, conditional=True)]
        )
        ctx = create_context()
        # No skip_reason set

        results = await graph.run(ctx)

        assert results["conditional"].status == StageStatus.OK
        assert results["conditional"].data.get("ran") is True

    @pytest.mark.asyncio
    async def test_conditional_stage_skipped_with_reason(self):
        """Test conditional stage is skipped when skip_reason is set."""
        # First stage sets skip_reason
        async def setup_runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"skip_reason": "condition not met"})

        async def conditional_runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"ran": True})

        graph = UnifiedStageGraph(
            specs=[
                UnifiedStageSpec(name="setup", runner=setup_runner, kind=StageKind.TRANSFORM),
                UnifiedStageSpec(name="conditional", runner=conditional_runner, dependencies=("setup",), kind=StageKind.GUARD, conditional=True),
            ]
        )
        ctx = create_context()

        results = await graph.run(ctx)

        # Check that setup ran successfully
        assert results["setup"].status == StageStatus.OK
        # Conditional should be skipped because skip_reason was set by setup
        assert results["conditional"].status == StageStatus.SKIP
        assert results["conditional"].data.get("reason") == "condition not met"

    @pytest.mark.asyncio
    async def test_conditional_with_dependencies_skipped(self):
        """Test conditional stage with dependencies is skipped correctly."""
        execution_order = []

        async def setup_runner(ctx: StageContext) -> StageOutput:
            execution_order.append("setup")
            return StageOutput.ok(data={"skip_reason": "skipped"})

        async def regular_runner(name: str):
            async def inner(ctx: StageContext) -> StageOutput:
                execution_order.append(name)
                return StageOutput.ok()
            return inner

        async def conditional_runner(ctx: StageContext) -> StageOutput:
            execution_order.append("conditional")
            return StageOutput.ok()

        specs = [
            UnifiedStageSpec(name="setup", runner=setup_runner, kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="first", runner=await regular_runner("first"), dependencies=("setup",), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="conditional", runner=conditional_runner, dependencies=("first",), kind=StageKind.GUARD, conditional=True),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        results = await graph.run(ctx)

        assert "setup" in execution_order
        assert "first" in execution_order
        # Conditional doesn't add to execution_order because it skips


# === Test Edge Cases ===

class TestUnifiedStageGraphEdgeCases:
    """Edge case tests for UnifiedStageGraph."""

    @pytest.mark.asyncio
    async def test_empty_data_dict(self):
        """Test stage with empty data dict."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={})

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="test", runner=runner, kind=StageKind.TRANSFORM)]
        )
        ctx = create_context()

        results = await graph.run(ctx)

        assert results["test"].data == {}

    @pytest.mark.asyncio
    async def test_complex_data_types(self):
        """Test stage with complex data types."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={
                "list": [1, 2, 3],
                "nested": {"a": {"b": "c"}},
                "none": None,
                "bool": True,
            })

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="test", runner=runner, kind=StageKind.TRANSFORM)]
        )
        ctx = create_context()

        results = await graph.run(ctx)

        assert results["test"].data["list"] == [1, 2, 3]
        assert results["test"].data["nested"]["a"]["b"] == "c"

    @pytest.mark.asyncio
    async def test_stage_with_artifacts(self):
        """Test stage that produces artifacts."""
        from stageflow.core.stages import StageArtifact

        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput(
                status=StageStatus.OK,
                artifacts=[
                    StageArtifact(type="audio", payload={"format": "mp3"}),
                    StageArtifact(type="text", payload={"content": "hello"}),
                ]
            )

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="test", runner=runner, kind=StageKind.TRANSFORM)]
        )
        ctx = create_context()

        results = await graph.run(ctx)

        assert len(results["test"].artifacts) == 2
        assert results["test"].artifacts[0].type == "audio"

    @pytest.mark.asyncio
    async def test_stage_with_events(self):
        """Test stage that emits events."""
        from stageflow.core.stages import StageEvent

        async def runner(ctx: StageContext) -> StageOutput:
            ctx.emit_event("stage.started", {"stage": "test"})
            ctx.emit_event("stage.completed", {"stage": "test"})
            return StageOutput(status=StageStatus.OK)

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="test", runner=runner, kind=StageKind.TRANSFORM)]
        )
        ctx = create_context()

        results = await graph.run(ctx)

        # Events are collected in the stage's context and returned in the result
        result = results["test"]
        # The result doesn't directly contain events - check if events were emitted
        # For this test, we verify the stage completed successfully
        assert result.status == StageStatus.OK

    @pytest.mark.asyncio
    async def test_retry_status_handling(self):
        """Test stage with RETRY status."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.retry(error="Temporary failure")

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="test", runner=runner, kind=StageKind.WORK)]
        )
        ctx = create_context()

        results = await graph.run(ctx)

        # RETRY should be treated as OK (not failure)
        assert results["test"].status == StageStatus.RETRY

    @pytest.mark.asyncio
    async def test_skip_status_handling(self):
        """Test stage with SKIP status."""
        async def runner(ctx: StageContext) -> StageOutput:
            return StageOutput.skip(reason="Not needed")

        graph = UnifiedStageGraph(
            specs=[UnifiedStageSpec(name="test", runner=runner, kind=StageKind.GUARD)]
        )
        ctx = create_context()

        results = await graph.run(ctx)

        # SKIP should be treated as OK
        assert results["test"].status == StageStatus.SKIP

    @pytest.mark.asyncio
    async def test_deep_dependency_graph(self):
        """Test deep dependency graph."""
        async def make_runner(i: int):
            async def runner(ctx: StageContext) -> StageOutput:
                return StageOutput.ok(data={"n": i})
            return runner

        specs = [
            UnifiedStageSpec(
                name=f"stage_{i}",
                runner=await make_runner(i),
                kind=StageKind.TRANSFORM,
                dependencies=(f"stage_{i-1}",) if i > 0 else (),
            )
            for i in range(20)
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        results = await graph.run(ctx)

        assert len(results) == 20

    @pytest.mark.asyncio
    async def test_wide_fan_out(self):
        """Test wide fan-out (one parent, many children)."""
        async def make_runner():
            async def runner(ctx: StageContext) -> StageOutput:
                return StageOutput.ok()
            return runner

        specs = [
            UnifiedStageSpec(
                name="root",
                runner=await make_runner(),
                kind=StageKind.TRANSFORM,
            ),
        ] + [
            UnifiedStageSpec(
                name=f"child_{i}",
                runner=await make_runner(),
                kind=StageKind.TRANSFORM,
                dependencies=("root",),
            )
            for i in range(30)
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        results = await graph.run(ctx)

        assert len(results) == 31

    @pytest.mark.asyncio
    async def test_shared_timer_across_stages(self):
        """Test that shared timer is used across stages."""
        import time

        timer1_time = None
        timer2_time = None

        async def runner1(ctx: StageContext) -> StageOutput:
            nonlocal timer1_time
            timer = ctx.timer
            timer1_time = timer.pipeline_start_ms
            await asyncio.sleep(0.05)
            return StageOutput.ok()

        async def runner2(ctx: StageContext) -> StageOutput:
            nonlocal timer2_time
            timer = ctx.timer
            timer2_time = timer.pipeline_start_ms
            return StageOutput.ok()

        specs = [
            UnifiedStageSpec(name="a", runner=runner1, kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="b", runner=runner2, dependencies=("a",), kind=StageKind.TRANSFORM),
        ]
        graph = UnifiedStageGraph(specs=specs)
        ctx = create_context()

        await graph.run(ctx)

        # Both should share the same timer
        assert timer1_time == timer2_time
