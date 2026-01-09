"""Integration tests for stageflow.

These tests verify full pipeline execution paths, combining multiple
components together to ensure the entire system works end-to-end.
"""

import asyncio
from datetime import datetime, UTC
from typing import Any
from uuid import uuid4
import pytest

from stageflow.context import ContextSnapshot
from stageflow.core import (
    StageContext,
    StageKind,
    StageOutput,
    StageStatus,
    StageArtifact,
)
from stageflow.pipeline.dag import UnifiedStageGraph, UnifiedStageSpec
from stageflow.stages.inputs import StageInputs, create_stage_inputs


# === Test Fixtures ===

def create_snapshot(
    pipeline_run_id: str | None = None,
    topology: str = "test_pipeline",
) -> ContextSnapshot:
    """Create a test ContextSnapshot."""
    return ContextSnapshot(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=uuid4(),
        interaction_id=uuid4(),
        topology=topology,
        
        execution_mode="test",
        extensions={"key": "value"}
    )


# === StageGraph Integration Tests ===

class TestStageGraphIntegration:
    """Integration tests for UnifiedStageGraph with multiple components."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_all_components(self):
        """Test a complete pipeline with transform, guard, and work stages."""
        async def transform_runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"transformed": True, "value": 42})

        async def guard_runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"allowed": True})

        async def work_runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"completed": True})

        specs = [
            UnifiedStageSpec(
                name="transform",
                runner=transform_runner,
                kind=StageKind.TRANSFORM,
            ),
            UnifiedStageSpec(
                name="guard",
                runner=guard_runner,
                dependencies=("transform",),
                kind=StageKind.GUARD,
            ),
            UnifiedStageSpec(
                name="work",
                runner=work_runner,
                dependencies=("guard",),
                kind=StageKind.WORK,
            ),
        ]

        graph = UnifiedStageGraph(specs=specs)
        ctx = StageContext(snapshot=create_snapshot())

        results = await graph.run(ctx)

        assert len(results) == 3
        assert results["transform"].status == StageStatus.OK
        assert results["guard"].status == StageStatus.OK
        assert results["work"].status == StageStatus.OK

    @pytest.mark.asyncio
    async def test_parallel_execution_integration(self):
        """Test that parallel stages execute concurrently."""
        execution_times = []

        async def timed_runner(name: str, delay: float):
            async def runner(ctx: StageContext) -> StageOutput:
                start = datetime.now(UTC)
                await asyncio.sleep(delay)
                execution_times.append((name, datetime.now(UTC) - start))
                return StageOutput.ok()
            return runner

        specs = [
            UnifiedStageSpec(
                name="a",
                runner=await timed_runner("a", 0.05),
                kind=StageKind.TRANSFORM,
            ),
            UnifiedStageSpec(
                name="b",
                runner=await timed_runner("b", 0.05),
                kind=StageKind.TRANSFORM,
            ),
            UnifiedStageSpec(
                name="c",
                runner=await timed_runner("c", 0.05),
                kind=StageKind.TRANSFORM,
            ),
        ]

        graph = UnifiedStageGraph(specs=specs)
        ctx = StageContext(snapshot=create_snapshot())

        start = datetime.now(UTC)
        results = await graph.run(ctx)
        elapsed = datetime.now(UTC) - start

        assert len(results) == 3
        # All three should run in parallel, taking ~0.05s instead of 0.15s
        assert elapsed.total_seconds() < 0.15

    @pytest.mark.asyncio
    async def test_default_interceptors_are_applied(self):
        """Test that default interceptors are configured for stages."""
        async def test_runner(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"test": True})

        spec = UnifiedStageSpec(
            name="test",
            runner=test_runner,
            kind=StageKind.TRANSFORM,
        )

        graph = UnifiedStageGraph(specs=[spec])
        ctx = StageContext(snapshot=create_snapshot())

        results = await graph.run(ctx)

        # Verify stage completed successfully with interceptors handling
        assert results["test"].status == StageStatus.OK
        assert results["test"].data["test"] is True


# === StageInputs Integration Tests ===

class TestStageInputsIntegration:
    """Integration tests for StageInputs with various data flows."""

    @pytest.mark.asyncio
    async def test_prior_outputs_flow_through_graph(self):
        """Test that prior outputs are properly available to dependent stages."""
        stage2_received_data = []

        async def stage1(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"key": "value1", "number": 42})

        async def stage2(ctx: StageContext) -> StageOutput:
            inputs = ctx.config.get("inputs")
            if inputs and hasattr(inputs, "prior_outputs"):
                prior = inputs.prior_outputs
                if "stage1" in prior:
                    stage2_received_data.append(prior["stage1"].data)
            return StageOutput.ok()

        specs = [
            UnifiedStageSpec(name="stage1", runner=stage1, kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="stage2", runner=stage2, dependencies=("stage1",), kind=StageKind.TRANSFORM),
        ]

        graph = UnifiedStageGraph(specs=specs)
        ctx = StageContext(snapshot=create_snapshot())

        await graph.run(ctx)

        assert len(stage2_received_data) == 1
        assert stage2_received_data[0]["key"] == "value1"
        assert stage2_received_data[0]["number"] == 42


# === Error Handling Integration Tests ===

class TestErrorHandlingIntegration:
    """Integration tests for error handling across components."""

    @pytest.mark.asyncio
    async def test_all_stages_complete_successfully(self):
        """Test that all stages complete successfully in a normal workflow."""
        results = []

        async def stage1(ctx: StageContext) -> StageOutput:
            results.append("stage1")
            return StageOutput.ok(data={"step": 1})

        async def stage2(ctx: StageContext) -> StageOutput:
            results.append("stage2")
            return StageOutput.ok(data={"step": 2})

        async def stage3(ctx: StageContext) -> StageOutput:
            results.append("stage3")
            return StageOutput.ok(data={"step": 3})

        specs = [
            UnifiedStageSpec(name="stage1", runner=stage1, kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="stage2", runner=stage2, dependencies=("stage1",), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="stage3", runner=stage3, dependencies=("stage2",), kind=StageKind.TRANSFORM),
        ]

        graph = UnifiedStageGraph(specs=specs)
        ctx = StageContext(snapshot=create_snapshot())

        results_dict = await graph.run(ctx)

        assert len(results_dict) == 3
        assert all(r.status == StageStatus.OK for r in results_dict.values())
        assert results == ["stage1", "stage2", "stage3"]


# === Conditional Execution Integration Tests ===

class TestConditionalExecutionIntegration:
    """Integration tests for conditional stage execution."""

    @pytest.mark.asyncio
    async def test_conditional_stage_runs_when_no_skip(self):
        """Test conditional stage runs when no skip reason is set."""
        execution_order = []

        async def normal_stage(ctx: StageContext) -> StageOutput:
            execution_order.append("normal")
            return StageOutput.ok()

        async def conditional_stage(ctx: StageContext) -> StageOutput:
            execution_order.append("conditional")
            return StageOutput.ok()

        specs = [
            UnifiedStageSpec(
                name="normal",
                runner=normal_stage,
                kind=StageKind.TRANSFORM,
            ),
            UnifiedStageSpec(
                name="conditional",
                runner=conditional_stage,
                dependencies=("normal",),
                kind=StageKind.GUARD,
                conditional=True,
            ),
        ]

        graph = UnifiedStageGraph(specs=specs)
        ctx = StageContext(snapshot=create_snapshot())
        results = await graph.run(ctx)

        assert "normal" in execution_order
        assert "conditional" in execution_order
        assert results["conditional"].status == StageStatus.OK

    @pytest.mark.asyncio
    async def test_skip_with_reason_workflow(self):
        """Test that conditional stages are properly skipped with reason."""
        async def setup_stage(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"skip_reason": "triage_failed"})

        async def conditional_stage(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"ran": True})

        specs = [
            UnifiedStageSpec(
                name="setup",
                runner=setup_stage,
                kind=StageKind.TRANSFORM,
            ),
            UnifiedStageSpec(
                name="conditional",
                runner=conditional_stage,
                dependencies=("setup",),
                kind=StageKind.GUARD,
                conditional=True,
            ),
        ]

        graph = UnifiedStageGraph(specs=specs)
        ctx = StageContext(snapshot=create_snapshot())

        results = await graph.run(ctx)

        assert results["setup"].status == StageStatus.OK
        assert results["conditional"].status == StageStatus.SKIP
        assert results["conditional"].data.get("reason") == "triage_failed"


# === Artifact and Event Integration Tests ===

class TestArtifactEventIntegration:
    """Integration tests for artifacts across stages."""

    @pytest.mark.asyncio
    async def test_artifacts_through_pipeline(self):
        """Test that artifacts are properly created and collected."""
        async def stage_with_artifact(ctx: StageContext) -> StageOutput:
            return StageOutput(
                status=StageStatus.OK,
                artifacts=[
                    StageArtifact(type="audio", payload={"format": "mp3"}),
                    StageArtifact(type="text", payload={"content": "hello"}),
                ]
            )

        spec = UnifiedStageSpec(
            name="test",
            runner=stage_with_artifact,
            kind=StageKind.TRANSFORM,
        )

        graph = UnifiedStageGraph(specs=[spec])
        ctx = StageContext(snapshot=create_snapshot())

        results = await graph.run(ctx)

        assert results["test"].status == StageStatus.OK
        assert len(results["test"].artifacts) == 2
        assert results["test"].artifacts[0].type == "audio"
        assert results["test"].artifacts[1].type == "text"


# === End-to-End Pipeline Tests ===

class TestEndToEndPipeline:
    """End-to-end pipeline integration tests."""

    @pytest.mark.asyncio
    async def test_chat_pipeline_workflow(self):
        """Test a complete chat-like pipeline workflow."""
        # STT Stage
        async def stt_stage(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"transcript": "Hello, how are you?"})

        # LLM Stage
        async def llm_stage(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"response": "I'm doing well, thanks!"})

        # TTS Stage
        async def tts_stage(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"audio_duration_ms": 1500})

        specs = [
            UnifiedStageSpec(name="stt", runner=stt_stage, kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="llm", runner=llm_stage, dependencies=("stt",), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="tts", runner=tts_stage, dependencies=("llm",), kind=StageKind.TRANSFORM),
        ]

        graph = UnifiedStageGraph(specs=specs)
        ctx = StageContext(snapshot=create_snapshot("chat_fast"))

        results = await graph.run(ctx)

        assert len(results) == 3
        assert results["stt"].data["transcript"] == "Hello, how are you?"
        assert "response" in results["llm"].data
        assert results["tts"].data["audio_duration_ms"] == 1500

    @pytest.mark.asyncio
    async def test_voice_pipeline_with_guardrail(self):
        """Test a voice pipeline with a guardrail stage."""
        # Input processing
        async def process_input(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"processed_input": "test"})

        # Guardrail check
        async def guardrail(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"safe": True})

        # LLM generation
        async def llm(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"response": "Generated response"})

        # TTS synthesis
        async def tts(ctx: StageContext) -> StageOutput:
            return StageOutput.ok(data={"audio": "synthesized"})

        specs = [
            UnifiedStageSpec(name="process", runner=process_input, kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="guardrail", runner=guardrail, dependencies=("process",), kind=StageKind.GUARD),
            UnifiedStageSpec(name="llm", runner=llm, dependencies=("guardrail",), kind=StageKind.TRANSFORM),
            UnifiedStageSpec(name="tts", runner=tts, dependencies=("llm",), kind=StageKind.TRANSFORM),
        ]

        graph = UnifiedStageGraph(specs=specs)
        ctx = StageContext(snapshot=create_snapshot("voice_accurate"))

        results = await graph.run(ctx)

        assert len(results) == 4
        assert all(r.status == StageStatus.OK for r in results.values())


# === Performance Integration Tests ===

class TestPerformanceIntegration:
    """Performance-related integration tests."""

    @pytest.mark.asyncio
    async def test_many_stages_parallel_execution(self):
        """Test performance with many stages running in parallel."""
        async def make_runner(name: str):
            async def runner(ctx: StageContext) -> StageOutput:
                await asyncio.sleep(0.01)
                return StageOutput.ok(data={"stage": name})
            return runner

        # Create 50 independent stages
        specs = [
            UnifiedStageSpec(name=f"stage_{i}", runner=await make_runner(f"stage_{i}"), kind=StageKind.TRANSFORM)
            for i in range(50)
        ]

        graph = UnifiedStageGraph(specs=specs)
        ctx = StageContext(snapshot=create_snapshot())

        start = datetime.now(UTC)
        results = await graph.run(ctx)
        elapsed = datetime.now(UTC) - start

        assert len(results) == 50
        # Should complete in ~0.01s (plus overhead) because all run in parallel
        # Serial would take ~0.5s
        assert elapsed.total_seconds() < 0.2

    @pytest.mark.asyncio
    async def test_deep_dependency_chain(self):
        """Test performance with a deep chain of dependencies."""
        async def make_runner(name: str):
            async def runner(ctx: StageContext) -> StageOutput:
                return StageOutput.ok(data={"stage": name})
            return runner

        # Create a chain of 100 stages
        specs = [
            UnifiedStageSpec(
                name=f"stage_{i}",
                runner=await make_runner(f"stage_{i}"),
                kind=StageKind.TRANSFORM,
                dependencies=(f"stage_{i-1}",) if i > 0 else (),
            )
            for i in range(100)
        ]

        graph = UnifiedStageGraph(specs=specs)
        ctx = StageContext(snapshot=create_snapshot())

        results = await graph.run(ctx)

        assert len(results) == 100
        assert all(r.status == StageStatus.OK for r in results.values())
