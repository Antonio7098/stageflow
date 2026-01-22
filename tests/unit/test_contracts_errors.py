from __future__ import annotations

from stageflow.contracts import ContractErrorInfo


def test_contract_error_info_serialization() -> None:
    info = ContractErrorInfo(
        code="TEST-001",
        summary="Test summary",
        fix_hint="Fix it",
        doc_url="https://example.com",
        context={"stage": "test_stage"},
    )
    payload = info.to_dict()
    assert payload["code"] == "TEST-001"
    assert payload["summary"] == "Test summary"
    assert payload["fix_hint"] == "Fix it"
    assert payload["doc_url"] == "https://example.com"
    assert payload["context"]["stage"] == "test_stage"


def test_with_context_merges_new_context() -> None:
    base = ContractErrorInfo(
        code="BASE",
        summary="Base",
        context={"a": 1},
    )
    merged = base.with_context(b=2, a=99)  # 'a' should be overridden
    assert merged.context == {"a": 99, "b": 2}
    # Original is immutable
    assert base.context == {"a": 1}


def test_with_context_preserves_other_fields() -> None:
    base = ContractErrorInfo(
        code="BASE",
        summary="Base",
        fix_hint="Fix",
        doc_url="https://example.com",
    )
    merged = base.with_context(extra="value")
    assert merged.code == "BASE"
    assert merged.summary == "Base"
    assert merged.fix_hint == "Fix"
    assert merged.doc_url == "https://example.com"
    assert merged.context == {"extra": "value"}
