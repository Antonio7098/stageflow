from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from pydantic import BaseModel

from stageflow.contracts import TypedStageOutput, registry


class ExamplePayload(BaseModel):
    text: str
    count: int = 0


class ExamplePayloadV2(BaseModel):
    text: str
    count: int
    summary: str


@pytest.fixture(autouse=True)
def clear_contract_registry() -> None:
    """Ensure the shared registry is reset between tests."""

    registry.clear()
    yield
    registry.clear()


def test_typed_output_validates_dict_payload() -> None:
    typed = TypedStageOutput(ExamplePayload)

    model = typed.validate({"text": "done"})

    assert model.text == "done"
    assert model.count == 0


def test_typed_output_ok_propagates_default_version() -> None:
    typed = TypedStageOutput(ExamplePayload, default_version="v1")

    output = typed.ok({"text": "done"})

    assert output.version == "v1"
    assert output.data == {"text": "done", "count": 0}


def test_typed_output_ok_can_override_version() -> None:
    typed = TypedStageOutput(ExamplePayload, default_version="v1")

    output = typed.ok({"text": "done"}, version="v2")

    assert output.version == "v2"


@pytest.mark.asyncio
async def test_typed_output_ok_async_supports_version_factory() -> None:
    called = False

    def version_factory() -> str:
        nonlocal called
        called = True
        return "ts-001"

    typed = TypedStageOutput(ExamplePayload, version_factory=version_factory)

    async def payload_factory() -> dict[str, str]:
        await asyncio.sleep(0)
        return {"text": "async"}

    output = await typed.ok_async(payload_factory)

    assert output.version == "ts-001"
    assert called is True


def test_register_contract_persists_metadata() -> None:
    typed = TypedStageOutput(ExamplePayload, default_version="v1")

    metadata = typed.register_contract(stage="summary", description="First release")

    assert metadata.stage == "summary"
    assert metadata.version == "v1"
    assert registry.get("summary", "v1") is not None


def test_register_contract_requires_version() -> None:
    typed = TypedStageOutput(ExamplePayload)

    with pytest.raises(ValueError, match="version must be provided"):
        typed.register_contract(stage="summary")


def test_contract_registry_diff_detects_breaking_changes() -> None:
    registry.register(stage="summary", version="v1", model=ExamplePayload)
    registry.register(stage="summary", version="v2", model=ExamplePayloadV2)

    report = registry.diff(stage="summary", from_version="v1", to_version="v2")

    assert report.is_compatible is False
    assert any("Required field" in change for change in report.breaking_changes)


def test_timestamp_version_returns_iso_string() -> None:
    value = TypedStageOutput.timestamp_version()

    # Should be parseable by datetime.fromisoformat
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
