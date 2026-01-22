from __future__ import annotations

from stageflow.contracts import ContractSuggestion, get_contract_suggestion, register_suggestion


def test_register_and_retrieve_suggestion() -> None:
    suggestion = ContractSuggestion(
        code="TEST-001",
        title="Test Suggestion",
        summary="A test suggestion",
        fix_steps=["Do A", "Do B"],
        doc_url="https://example.com/test",
    )
    register_suggestion(suggestion)

    retrieved = get_contract_suggestion("TEST-001")
    assert retrieved is not None
    assert retrieved.code == "TEST-001"
    assert retrieved.title == "Test Suggestion"
    assert retrieved.fix_steps == ["Do A", "Do B"]
    assert retrieved.doc_url == "https://example.com/test"


def test_missing_suggestion_returns_none() -> None:
    result = get_contract_suggestion("NONEXISTENT")
    assert result is None


def test_register_overwrites_existing() -> None:
    register_suggestion(
        ContractSuggestion(
            code="OVERWRITE-001",
            title="Original",
            summary="Original summary",
            fix_steps=["Original step"],
        )
    )
    register_suggestion(
        ContractSuggestion(
            code="OVERWRITE-001",
            title="Updated",
            summary="Updated summary",
            fix_steps=["Updated step"],
        )
    )
    result = get_contract_suggestion("OVERWRITE-001")
    assert result is not None
    assert result.title == "Updated"
    assert result.summary == "Updated summary"
    assert result.fix_steps == ["Updated step"]


def test_preloaded_suggestions_are_available() -> None:
    # Verify a few default suggestions are present
    cycle = get_contract_suggestion("CONTRACT-004-CYCLE")
    assert cycle is not None
    assert "cycle" in cycle.title.lower()

    missing = get_contract_suggestion("CONTRACT-004-MISSING_DEP")
    assert missing is not None
    assert "missing" in missing.title.lower()

    empty = get_contract_suggestion("CONTRACT-004-EMPTY")
    assert empty is not None
    assert "empty" in empty.title.lower()
