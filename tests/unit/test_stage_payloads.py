from __future__ import annotations

from uuid import uuid4

import pytest

from stageflow.context import ContextSnapshot, RunIdentity
from stageflow.core import PipelineTimer, StageContext, StageOutput
from stageflow.pipeline.results import PipelineResults
from stageflow.stages.inputs import StageInputs
from stageflow.stages.payloads import (
    StagePayloadResult,
    cancel_output,
    fail_output,
    ok_output,
    payload_from_inputs,
    payload_from_results,
    summary_from_output,
)


def _snapshot() -> ContextSnapshot:
    return ContextSnapshot(
        run_id=RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        ),
        topology="test",
        execution_mode="unit",
    )


def test_ok_output_wraps_payload_and_summary() -> None:
    output = ok_output(
        StagePayloadResult(
            payload={"answer": 42},
            summary={"items": 1},
        )
    )

    assert output.data["payload"] == {"answer": 42}
    assert output.data["summary"] == {"items": 1}


def test_cancel_and_fail_helpers_preserve_summary_shape() -> None:
    cancelled = cancel_output(
        StagePayloadResult(payload={"status": "partial"}, summary={"step": "draft"}),
        reason="user requested",
    )
    failed = fail_output(error="boom", payload={"attempt": 1}, summary={"step": "persist"})

    assert cancelled.data["payload"] == {"status": "partial"}
    assert cancelled.data["summary"] == {"step": "draft"}
    assert failed.data["payload"] == {"attempt": 1}
    assert failed.data["summary"] == {"step": "persist"}


def test_payload_from_inputs_reads_typed_payload() -> None:
    snapshot = _snapshot()
    prior_outputs = {
        "upstream": ok_output(StagePayloadResult(payload={"value": "done"}, summary={"ok": True}))
    }
    ctx = StageContext(
        snapshot=snapshot,
        inputs=StageInputs(
            snapshot=snapshot,
            prior_outputs=prior_outputs,
            declared_deps=frozenset({"upstream"}),
            stage_name="consumer",
        ),
        stage_name="consumer",
        timer=PipelineTimer(),
    )

    payload = payload_from_inputs(ctx, "upstream", expected_type=dict)

    assert payload == {"value": "done"}


def test_payload_from_results_reads_typed_payload() -> None:
    results = PipelineResults(
        {
            "final": ok_output(StagePayloadResult(payload=["a", "b"], summary={"count": 2}))
        }
    )

    payload = payload_from_results(results, "final", expected_type=list)

    assert payload == ["a", "b"]


def test_payload_helpers_raise_on_type_mismatch() -> None:
    results = PipelineResults(
        {
            "final": ok_output(StagePayloadResult(payload={"value": "done"}))
        }
    )

    with pytest.raises(TypeError, match="did not match"):
        payload_from_results(results, "final", expected_type=list)


def test_summary_from_output_returns_only_valid_summary_dict() -> None:
    output = StageOutput.ok(data={"payload": 1, "summary": {"count": 1}})

    assert summary_from_output(output) == {"count": 1}
