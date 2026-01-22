"""Contract suggestion registry mapping error codes to remediation hints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContractSuggestion:
    """Structured remediation info for a contract violation."""

    code: str
    title: str
    summary: str
    fix_steps: list[str]
    doc_url: str | None = None


_SUGGESTIONS: dict[str, ContractSuggestion] = {}


def register_suggestion(suggestion: ContractSuggestion) -> None:
    """Register a suggestion for a contract code."""

    _SUGGESTIONS[suggestion.code] = suggestion


def get_contract_suggestion(code: str) -> ContractSuggestion | None:
    """Return suggestion metadata for an error code if registered."""

    return _SUGGESTIONS.get(code)


# Preload default suggestions for common pipeline contract violations.
register_suggestion(
    ContractSuggestion(
        code="CONTRACT-004-CYCLE",
        title="Dependency Cycle Detected",
        summary="Stages depend on each other in a loop, preventing execution order.",
        fix_steps=[
            "Review the reported cycle path",
            "Remove at least one dependency edge to break the loop",
            "Re-run pipeline validation or the contracts CLI",
        ],
        doc_url="https://github.com/stageflow/stageflow/blob/main/docs/advanced/error-messages.md#dependency-cycles",
    )
)

register_suggestion(
    ContractSuggestion(
        code="CONTRACT-004-MISSING_DEP",
        title="Missing Stage Dependency",
        summary="A stage declares a dependency on a stage that is not in the pipeline graph.",
        fix_steps=[
            "Ensure the referenced stage is added to the pipeline",
            "Or remove/rename the dependency if it is not needed",
        ],
        doc_url="https://github.com/stageflow/stageflow/blob/main/docs/advanced/error-messages.md#missing-stage-dependencies",
    )
)

register_suggestion(
    ContractSuggestion(
        code="CONTRACT-004-SELF_DEP",
        title="Stage Depends on Itself",
        summary="A stage lists itself in its dependency tuple, which creates an impossible prerequisite.",
        fix_steps=["Remove the self-reference from the dependency list"],
        doc_url="https://github.com/stageflow/stageflow/blob/main/docs/advanced/error-messages.md#self-dependencies",
    )
)

register_suggestion(
    ContractSuggestion(
        code="CONTRACT-004-CONFLICT",
        title="Conflicting Stage Definition",
        summary="The same stage name is defined multiple times with incompatible specs when composing pipelines.",
        fix_steps=[
            "Ensure composed pipelines define the stage with the same runner and dependency set",
            "Rename one of the stages if they represent different logic",
        ],
        doc_url="https://github.com/stageflow/stageflow/blob/main/docs/advanced/error-messages.md#conflicting-stage-definitions",
    )
)

register_suggestion(
    ContractSuggestion(
        code="CONTRACT-004-ORPHAN",
        title="Isolated Stage Warning",
        summary="A stage is neither depended on nor depends on any other stage, which usually indicates misconfiguration.",
        fix_steps=[
            "Add dependencies so the stage participates in the pipeline",
            "Or remove the stage if it should not run",
        ],
        doc_url="https://github.com/stageflow/stageflow/blob/main/docs/advanced/error-messages.md#isolated-stages",
    )
)

register_suggestion(
    ContractSuggestion(
        code="CONTRACT-004-EMPTY",
        title="Empty Pipeline",
        summary="Attempted to build or execute a pipeline without any stages.",
        fix_steps=["Add at least one stage before invoking Pipeline.build()"],
        doc_url="https://github.com/stageflow/stageflow/blob/main/docs/advanced/error-messages.md#empty-pipelines",
    )
)
