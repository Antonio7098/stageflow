"""Shared contract error metadata types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ContractErrorInfo:
    """Structured metadata for surfaced contract violations.

    Attributes:
        code: Stable identifier that maps to a runbook or tracker entry.
        summary: Human-readable description of the issue.
        fix_hint: Optional remediation guidance that can be surfaced to users.
        doc_url: Optional documentation link for deeper troubleshooting.
        context: Arbitrary structured data that helps downstream tooling render rich errors.
    """

    code: str
    summary: str
    fix_hint: str | None = None
    doc_url: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def with_context(self, **extra: Any) -> ContractErrorInfo:
        """Return a copy with additional context merged in."""

        merged = {**self.context, **extra}
        return ContractErrorInfo(
            code=self.code,
            summary=self.summary,
            fix_hint=self.fix_hint,
            doc_url=self.doc_url,
            context=merged,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the metadata for logging or API responses."""

        return {
            "code": self.code,
            "summary": self.summary,
            "fix_hint": self.fix_hint,
            "doc_url": self.doc_url,
            "context": self.context,
        }
