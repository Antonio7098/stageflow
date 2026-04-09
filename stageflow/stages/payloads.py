"""Typed helpers for the common payload + summary stage output pattern."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from stageflow.core import StageContext, StageOutput
from stageflow.stages.inputs import StageInputs

if TYPE_CHECKING:
    from stageflow.pipeline.results import PipelineResults

PAYLOAD_KEY = "payload"
SUMMARY_KEY = "summary"

_PayloadT = TypeVar("_PayloadT")


@dataclass(frozen=True, slots=True)
class StagePayloadResult(Generic[_PayloadT]):
    """Typed stage payload paired with optional summary metadata."""

    payload: _PayloadT
    summary: dict[str, Any] = field(default_factory=dict)


def ok_output(result: StagePayloadResult[Any]) -> StageOutput:
    """Encode a typed payload result as a successful StageOutput."""

    return StageOutput.ok(
        data={
            PAYLOAD_KEY: result.payload,
            SUMMARY_KEY: dict(result.summary),
        }
    )


def cancel_output(result: StagePayloadResult[Any], *, reason: str = "") -> StageOutput:
    """Encode a typed payload result as a cancelled StageOutput."""

    return StageOutput.cancel(
        reason=reason,
        data={
            PAYLOAD_KEY: result.payload,
            SUMMARY_KEY: dict(result.summary),
        },
    )


def fail_output(
    *,
    error: str,
    payload: Any = None,
    summary: dict[str, Any] | None = None,
) -> StageOutput:
    """Encode a typed payload result as a failed StageOutput."""

    return StageOutput.fail(
        error=error,
        data={
            PAYLOAD_KEY: payload,
            SUMMARY_KEY: dict(summary or {}),
        },
    )


def summary_from_output(output: StageOutput) -> dict[str, Any]:
    """Extract summary metadata from a StageOutput."""

    summary = output.data.get(SUMMARY_KEY, {})
    return dict(summary) if isinstance(summary, dict) else {}


def payload_from_inputs(
    ctx_or_inputs: StageContext | StageInputs,
    stage_name: str,
    *,
    expected_type: type[_PayloadT] | None = None,
) -> _PayloadT:
    """Read a dependency payload from StageContext inputs with optional type checks."""

    inputs = ctx_or_inputs.inputs if isinstance(ctx_or_inputs, StageContext) else ctx_or_inputs
    payload = inputs.require_from(stage_name, PAYLOAD_KEY)
    return _coerce_payload(
        payload,
        stage_name=stage_name,
        source="stage inputs",
        expected_type=expected_type,
    )


def payload_from_results(
    results: PipelineResults,
    stage_name: str,
    *,
    expected_type: type[_PayloadT] | None = None,
) -> _PayloadT:
    """Read a stage payload from final pipeline results with optional type checks."""

    payload = results.require_ok(stage_name).data[PAYLOAD_KEY]
    return _coerce_payload(
        payload,
        stage_name=stage_name,
        source="pipeline results",
        expected_type=expected_type,
    )


def _coerce_payload(
    payload: Any,
    *,
    stage_name: str,
    source: str,
    expected_type: type[_PayloadT] | None,
) -> _PayloadT:
    if expected_type is None:
        return cast(_PayloadT, payload)
    if not isinstance(payload, expected_type):
        raise TypeError(
            f"Stage {stage_name!r} payload from {source} did not match "
            f"{expected_type.__name__}; got {type(payload).__name__}"
        )
    return payload


__all__ = [
    "PAYLOAD_KEY",
    "SUMMARY_KEY",
    "StagePayloadResult",
    "cancel_output",
    "fail_output",
    "ok_output",
    "payload_from_inputs",
    "payload_from_results",
    "summary_from_output",
]
