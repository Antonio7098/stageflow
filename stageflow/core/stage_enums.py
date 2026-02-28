"""Stage enums for categorization and status."""

from enum import StrEnum


class StageKind(StrEnum):
    """Categorization of stage types for unified registry.

    All stages belong to exactly one kind which determines their
    lifecycle, typical input/output, and behavior patterns.
    """

    TRANSFORM = "transform"  # STT, TTS, LLM - change input form
    ENRICH = "enrich"  # Profile, Memory, Skills - add context
    ROUTE = "route"  # Router, Dispatcher - select path
    GUARD = "guard"  # Guardrails, Policy - validate
    WORK = "work"  # Assessment, Triage, Persist - side effects
    AGENT = "agent"  # Coach, Interviewer - main interactor


class StageStatus(StrEnum):
    """Possible outcomes from stage execution."""

    OK = "ok"  # Stage completed successfully
    SKIP = "skip"  # Stage was skipped (conditional)
    CANCEL = "cancel"  # Pipeline cancelled (no error, just stop)
    FAIL = "fail"  # Stage failed (error)
    RETRY = "retry"  # Stage failed but is retryable
