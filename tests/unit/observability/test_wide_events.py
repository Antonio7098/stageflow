from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from stageflow.observability import EVENT_VERSION, EventKind, WideEventEmitter
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult


class TestWideEventEmitter:
    def test_emit_stage_event_uses_graph_ready_shape(self) -> None:
        emitted: list[tuple[str, dict[str, object]]] = []

        class Sink:
            def try_emit(self, *, type, data):
                emitted.append((type, data))

        started_at = datetime.now(UTC)
        ended_at = started_at + timedelta(milliseconds=250)
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="demo",
            execution_mode="practice",
            event_sink=Sink(),
        )
        ctx.set_stage_metadata(
            "search",
            {
                "langgraph_node": "search",
                "langgraph_step": 2,
                "parent_observation_id": "root",
            },
        )
        result = StageResult(
            name="search",
            status="completed",
            started_at=started_at,
            ended_at=ended_at,
            data={"items": [1, 2]},
        )

        WideEventEmitter().emit_stage_event(ctx=ctx, result=result)

        event_type, payload = emitted[0]
        assert event_type == "stage.wide"
        assert payload["event_name"] == "stage.wide"
        assert payload["event_kind"] == EventKind.SPAN.value
        assert payload["event_version"] == EVENT_VERSION
        assert payload["type"] == "SPAN"
        assert payload["name"] == "search"
        assert payload["node"] == "search"
        assert payload["step"] == 2
        assert payload["parent_observation_id"] == "root"
        assert payload["pipeline_run_id"] == str(ctx.pipeline_run_id)

    def test_build_pipeline_payload_includes_trace_shape(self) -> None:
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="demo",
            execution_mode="practice",
        )
        started_at = datetime.now(UTC)
        result = StageResult(
            name="search",
            status="completed",
            started_at=started_at,
            ended_at=started_at + timedelta(milliseconds=50),
        )

        payload = WideEventEmitter.build_pipeline_payload(
            ctx=ctx,
            stage_results={"search": result},
            pipeline_name="demo",
            started_at=started_at,
        )

        assert payload["event_name"] == "pipeline.wide"
        assert payload["event_kind"] == EventKind.TRACE.value
        assert payload["event_version"] == EVENT_VERSION
        assert payload["type"] == "TRACE"
        assert payload["name"] == "demo"
        assert payload["pipeline_name"] == "demo"
        assert payload["stage_counts"] == {"completed": 1}
