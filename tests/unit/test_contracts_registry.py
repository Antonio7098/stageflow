from __future__ import annotations

import pytest
from pydantic import BaseModel

from stageflow.contracts import registry


class ModelV1(BaseModel):
    text: str
    count: int


class ModelV2(BaseModel):
    text: str
    count: int
    confidence: float


@pytest.fixture(autouse=True)
def clear_registry() -> None:
    registry.clear()
    yield
    registry.clear()


def test_register_and_get_metadata() -> None:
    meta = registry.register(
        stage="summarize",
        version="v1",
        model=ModelV1,
        description="First version",
    )
    assert meta.stage == "summarize"
    assert meta.version == "v1"
    assert meta.description == "First version"

    fetched = registry.get("summarize", "v1")
    assert fetched is not None
    assert fetched.stage == "summarize"
    assert fetched.version == "v1"


def test_register_same_version_with_same_model_returns_existing() -> None:
    first = registry.register(stage="test", version="v1", model=ModelV1)
    second = registry.register(stage="test", version="v1", model=ModelV1)
    assert first is second


def test_register_same_version_with_different_model_raises() -> None:
    registry.register(stage="dup", version="v1", model=ModelV1)
    with pytest.raises(ValueError, match="already registered with a different model"):
        registry.register(stage="dup", version="v1", model=ModelV2)


def test_list_filters_by_stage() -> None:
    registry.register(stage="a", version="v1", model=ModelV1)
    registry.register(stage="a", version="v2", model=ModelV2)
    registry.register(stage="b", version="v1", model=ModelV1)

    all_entries = registry.list()
    assert len(all_entries) == 3

    a_entries = registry.list(stage="a")
    assert [e.stage for e in a_entries] == ["a", "a"]
    assert [e.version for e in a_entries] == ["v1", "v2"]

    b_entries = registry.list(stage="b")
    assert len(b_entries) == 1
    assert b_entries[0].stage == "b"


def test_diff_detects_added_required_field_as_breaking() -> None:
    registry.register(stage="summarize", version="v1", model=ModelV1)
    registry.register(stage="summarize", version="v2", model=ModelV2)

    report = registry.diff("summarize", "v1", "v2")
    assert report.is_compatible is False
    assert any("required field" in change.lower() for change in report.breaking_changes)


def test_diff_detects_removed_field_as_breaking() -> None:
    class ModelV3(BaseModel):
        text: str

    registry.register(stage="summarize", version="v1", model=ModelV1)
    registry.register(stage="summarize", version="v3", model=ModelV3)

    report = registry.diff("summarize", "v1", "v3")
    assert report.is_compatible is False
    assert any("removed" in change.lower() for change in report.breaking_changes)


def test_diff_allows_optional_new_field_as_warning() -> None:
    class ModelV1(BaseModel):
        text: str

    class ModelV2(BaseModel):
        text: str
        confidence: float | None = None

    registry.register(stage="summarize", version="v1", model=ModelV1)
    registry.register(stage="summarize", version="v2", model=ModelV2)

    report = registry.diff("summarize", "v1", "v2")
    assert report.is_compatible is True
    assert any("optional field" in warn.lower() for warn in report.warnings)


def test_diff_raises_on_missing_version() -> None:
    registry.register(stage="summarize", version="v1", model=ModelV1)

    with pytest.raises(ValueError, match="Contract summarize@v2 not registered"):
        registry.diff("summarize", "v1", "v2")
