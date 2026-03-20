from __future__ import annotations

from uuid import uuid4

from stageflow.observability import EVENT_VERSION, EventKind
from stageflow.observability.envelope import build_payload, infer_event_kind
from stageflow.stages.context import PipelineContext


class TestInferEventKind:
    def test_pipeline_events_map_to_trace(self) -> None:
        assert infer_event_kind("pipeline.wide") is EventKind.TRACE

    def test_stage_events_map_to_span(self) -> None:
        assert infer_event_kind("stage.example.completed") is EventKind.SPAN

    def test_tool_events_map_to_tool(self) -> None:
        assert infer_event_kind("tool.completed") is EventKind.TOOL


class TestBuildPayload:
    def test_build_payload_includes_canonical_envelope(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "stageflow.observability.envelope.get_trace_context_dict",
            lambda: {
                "trace_id": "trace-123",
                "span_id": "span-456",
                "parent_span_id": "parent-789",
                "correlation_id": "corr-000",
            },
        )
        ctx = PipelineContext(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
            topology="demo",
            execution_mode="practice",
            metadata={"source": "test"},
        )

        payload = build_payload(
            event_type="tool.completed",
            ctx=ctx,
            data={"status": "completed", "metadata": {"provider": "openai"}},
        )

        assert payload["event_name"] == "tool.completed"
        assert payload["event_kind"] == EventKind.TOOL.value
        assert payload["event_version"] == EVENT_VERSION
        assert payload["pipeline_run_id"] == str(ctx.pipeline_run_id)
        assert payload["request_id"] == str(ctx.request_id)
        assert payload["session_id"] == str(ctx.session_id)
        assert payload["user_id"] == str(ctx.user_id)
        assert payload["org_id"] == str(ctx.org_id)
        assert payload["interaction_id"] == str(ctx.interaction_id)
        assert payload["trace_id"] == "trace-123"
        assert payload["span_id"] == "span-456"
        assert payload["parent_span_id"] == "parent-789"
        assert payload["correlation_id"] == "corr-000"
        assert payload["status"] == "completed"
        assert payload["metadata"] == {"source": "test", "provider": "openai"}
