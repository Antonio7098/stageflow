"""Guardrail SDK for content filtering and policy enforcement.

This module provides reusable guardrail utilities for:
- PII detection and redaction
- Content filtering (profanity, toxicity)
- Policy enforcement (rate limits, content length)

Usage:
    from stageflow.helpers import GuardrailStage, PIIDetector, ContentFilter

    # Create guardrail stage with multiple checks
    guardrail = GuardrailStage(
        checks=[
            PIIDetector(redact=True),
            ContentFilter(block_profanity=True),
        ],
        fail_on_violation=True,
    )

    pipeline = (
        Pipeline()
        .with_stage("guard_input", guardrail, StageKind.GUARD)
        .with_stage("llm", LLMStage(), StageKind.TRANSFORM, dependencies=("guard_input",))
    )
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from stageflow.core import StageContext, StageKind, StageOutput

logger = logging.getLogger("stageflow.helpers.guardrails")


_LEET_TRANSLATION = str.maketrans(
    {
        "0": "o",
        "1": "l",
        "2": "z",
        "3": "e",
        "4": "a",
        "5": "s",
        "6": "g",
        "7": "t",
        "8": "b",
        "9": "g",
        "@": "a",
        "$": "s",
        "!": "i",
        "+": "t",
    }
)


def _normalize_leetspeak(text: str) -> str:
    """Return text with common leetspeak substitutions normalized."""

    return text.translate(_LEET_TRANSLATION)


class ViolationType(Enum):
    """Types of policy violations."""

    PII_DETECTED = "pii_detected"
    PROFANITY = "profanity"
    TOXICITY = "toxicity"
    CONTENT_TOO_LONG = "content_too_long"
    RATE_LIMITED = "rate_limited"
    BLOCKED_TOPIC = "blocked_topic"
    INJECTION_ATTEMPT = "injection_attempt"
    CUSTOM = "custom"


@dataclass(frozen=True)
class PolicyViolation:
    """A detected policy violation.

    Attributes:
        type: The type of violation.
        message: Human-readable description.
        severity: How serious the violation is (0-1).
        metadata: Additional details about the violation.
        location: Where in the content the violation occurred.
    """

    type: ViolationType
    message: str
    severity: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)
    location: tuple[int, int] | None = None  # (start, end) character positions

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type.value,
            "message": self.message,
            "severity": self.severity,
            "metadata": self.metadata,
            "location": self.location,
        }


@dataclass
class GuardrailResult:
    """Result of a guardrail check.

    Attributes:
        passed: Whether the content passed the check.
        violations: List of violations found.
        transformed_content: Content after any transformations (e.g., redaction).
        metadata: Additional check metadata.
    """

    passed: bool
    violations: list[PolicyViolation] = field(default_factory=list)
    transformed_content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "transformed_content": self.transformed_content,
            "metadata": self.metadata,
        }


class GuardrailCheck(Protocol):
    """Protocol for guardrail checks.

    Implement this protocol to create custom guardrail checks.
    """

    def check(self, content: str, _context: dict[str, Any] | None = None) -> GuardrailResult:
        """Check content against the guardrail.

        Args:
            content: The content to check.
            context: Optional context (user info, session, etc.)

        Returns:
            GuardrailResult with pass/fail and any violations.
        """
        ...


@dataclass
class GuardrailConfig:
    """Configuration for guardrail behavior.

    Attributes:
        fail_on_violation: If True, return FAIL status; if False, just log violations.
        transform_content: If True, apply transformations (redaction, etc.).
        violation_threshold: Minimum severity to consider a violation (0-1).
        log_violations: Whether to log violations to event sink.
    """

    fail_on_violation: bool = True
    transform_content: bool = True
    violation_threshold: float = 0.0
    log_violations: bool = True


class PIIDetector:
    """Detects and optionally redacts PII from content.

    Detects:
    - Email addresses
    - Phone numbers (US formats)
    - Social Security Numbers
    - Credit card numbers
    - IP addresses

    Example:
        detector = PIIDetector(redact=True, redaction_char='*')
        result = detector.check("Call me at 555-123-4567")
        # result.transformed_content = "Call me at ***-***-****"
    """

    # PII patterns
    PATTERNS = {
        "email": (
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "Email address detected",
        ),
        "phone": (
            r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b",
            "Phone number detected",
        ),
        "ssn": (
            r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",
            "SSN detected",
        ),
        "credit_card": (
            r"\b(?:\d{4}[-.\s]?){3}\d{4}\b",
            "Credit card number detected",
        ),
        "ip_address": (
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
            "IP address detected",
        ),
    }

    def __init__(
        self,
        *,
        redact: bool = False,
        redaction_char: str = "*",
        detect_types: set[str] | None = None,
    ) -> None:
        """Initialize PII detector.

        Args:
            redact: Whether to redact detected PII.
            redaction_char: Character to use for redaction.
            detect_types: Set of PII types to detect (default: all).
        """
        self._redact = redact
        self._redaction_char = redaction_char
        self._detect_types = detect_types or set(self.PATTERNS.keys())

    def check(self, content: str, _context: dict[str, Any] | None = None) -> GuardrailResult:
        """Check content for PII."""
        violations: list[PolicyViolation] = []
        transformed = content

        for pii_type, (pattern, message) in self.PATTERNS.items():
            if pii_type not in self._detect_types:
                continue

            for match in re.finditer(pattern, content, re.IGNORECASE):
                violations.append(
                    PolicyViolation(
                        type=ViolationType.PII_DETECTED,
                        message=message,
                        severity=0.8,
                        metadata={"pii_type": pii_type},
                        location=(match.start(), match.end()),
                    )
                )

                if self._redact:
                    redacted = self._redaction_char * len(match.group())
                    transformed = (
                        transformed[: match.start()] + redacted + transformed[match.end() :]
                    )

        return GuardrailResult(
            passed=len(violations) == 0,
            violations=violations,
            transformed_content=transformed if self._redact else None,
            metadata={"pii_types_checked": list(self._detect_types)},
        )


class ContentFilter:
    r"""Filters content for profanity, toxicity, and blocked topics.

    Example:
        filter = ContentFilter(
            block_profanity=True,
            blocked_patterns=[r"competitor\s+product"],
        )
        result = filter.check("Our competitor product is bad")
    """

    # Basic profanity list (extend in production)
    DEFAULT_PROFANITY = {
        "damn",
        "hell",  # Mild
        # Add more as needed - keeping minimal for this example
    }

    def __init__(
        self,
        *,
        block_profanity: bool = True,
        profanity_list: set[str] | None = None,
        blocked_patterns: list[str] | None = None,
        max_severity: float = 0.3,
    ) -> None:
        """Initialize content filter.

        Args:
            block_profanity: Whether to check for profanity.
            profanity_list: Custom profanity list (default: built-in).
            blocked_patterns: Regex patterns for blocked content.
            max_severity: Severity for profanity violations.
        """
        self._block_profanity = block_profanity
        self._profanity = profanity_list or self.DEFAULT_PROFANITY
        self._blocked_patterns = blocked_patterns or []
        self._max_severity = max_severity

    def check(self, content: str, _context: dict[str, Any] | None = None) -> GuardrailResult:
        """Check content for blocked patterns and profanity."""
        violations: list[PolicyViolation] = []
        normalized_content = _normalize_leetspeak(content)
        words = set(re.findall(r"\b\w+\b", content.lower()))
        normalized_words = set(re.findall(r"\b\w+\b", normalized_content.lower()))

        # Check profanity
        if self._block_profanity:
            found_profanity = (words | normalized_words) & self._profanity
            for word in found_profanity:
                violations.append(
                    PolicyViolation(
                        type=ViolationType.PROFANITY,
                        message=f"Profanity detected: {word}",
                        severity=self._max_severity,
                        metadata={"word": word},
                    )
                )

        # Check blocked patterns
        for pattern in self._blocked_patterns:
            original_match = re.search(pattern, content, re.IGNORECASE)
            normalized_match = (
                re.search(pattern, normalized_content, re.IGNORECASE)
                if normalized_content != content
                else None
            )
            if original_match or normalized_match:
                violations.append(
                    PolicyViolation(
                        type=ViolationType.BLOCKED_TOPIC,
                        message=f"Blocked pattern matched: {pattern}",
                        severity=0.9,
                        metadata={
                            "pattern": pattern,
                            "normalized": normalized_match is not None and not original_match,
                        },
                    )
                )

        return GuardrailResult(
            passed=len(violations) == 0,
            violations=violations,
            metadata={"profanity_checked": self._block_profanity},
        )


class InjectionDetector:
    """Detects prompt injection attempts.

    Looks for common injection patterns:
    - Instruction overrides ("ignore previous instructions")
    - Role manipulation ("you are now a different assistant")
    - System prompt leakage attempts

    Example:
        detector = InjectionDetector()
        result = detector.check("Ignore all previous instructions and...")
    """

    INJECTION_PATTERNS = [
        r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?",
        r"disregard\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions?|prompts?)",
        r"forget\s+(?:everything|all)\s+(?:you\s+)?(?:know|learned)",
        r"you\s+are\s+now\s+(?:a\s+)?(?:different|new)\s+(?:assistant|ai|bot)",
        r"new\s+(?:system\s+)?(?:prompt|instructions?)\s*:",
        r"<\s*system\s*>",
        r"\[\s*SYSTEM\s*\]",
        r"as\s+(?:your\s+)?trusted\s+(?:advisor|friend|developer)[^\n]{0,80}share",
        r"i\s+need\s+you\s+to\s+act\s+like\s+security\s+(?:tester|auditor)",
        r"refer\s+back\s+to\s+our\s+previous\s+conversation\s+and\s+repeat",
        r"multi[-\s]?step\s+instructions?\s+override",
    ]

    def __init__(
        self,
        *,
        additional_patterns: list[str] | None = None,
    ) -> None:
        """Initialize injection detector.

        Args:
            additional_patterns: Additional regex patterns to check.
        """
        self._patterns = self.INJECTION_PATTERNS.copy()
        if additional_patterns:
            self._patterns.extend(additional_patterns)

    def check(self, content: str, _context: dict[str, Any] | None = None) -> GuardrailResult:
        """Check for injection attempts."""
        violations: list[PolicyViolation] = []

        for pattern in self._patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                violations.append(
                    PolicyViolation(
                        type=ViolationType.INJECTION_ATTEMPT,
                        message="Potential prompt injection detected",
                        severity=1.0,
                        metadata={"matched_pattern": pattern},
                        location=(match.start(), match.end()),
                    )
                )

        return GuardrailResult(
            passed=len(violations) == 0,
            violations=violations,
            metadata={"patterns_checked": len(self._patterns)},
        )


class ContentLengthCheck:
    """Checks content length against limits.

    Example:
        check = ContentLengthCheck(max_chars=10000, max_tokens=2048)
        result = check.check(long_content)
    """

    def __init__(
        self,
        *,
        max_chars: int = 0,
        max_tokens: int = 0,
        min_chars: int = 0,
    ) -> None:
        """Initialize length checker.

        Args:
            max_chars: Maximum character count (0 = no limit).
            max_tokens: Maximum approximate token count (0 = no limit).
            min_chars: Minimum character count.
        """
        self._max_chars = max_chars
        self._max_tokens = max_tokens
        self._min_chars = min_chars

    def check(self, content: str, _context: dict[str, Any] | None = None) -> GuardrailResult:
        """Check content length."""
        violations: list[PolicyViolation] = []
        char_count = len(content)
        token_count = char_count // 4  # Rough approximation

        if self._max_chars > 0 and char_count > self._max_chars:
            violations.append(
                PolicyViolation(
                    type=ViolationType.CONTENT_TOO_LONG,
                    message=f"Content exceeds max chars ({char_count} > {self._max_chars})",
                    severity=0.5,
                    metadata={"char_count": char_count, "limit": self._max_chars},
                )
            )

        if self._max_tokens > 0 and token_count > self._max_tokens:
            violations.append(
                PolicyViolation(
                    type=ViolationType.CONTENT_TOO_LONG,
                    message=f"Content exceeds max tokens (~{token_count} > {self._max_tokens})",
                    severity=0.5,
                    metadata={"token_count": token_count, "limit": self._max_tokens},
                )
            )

        if self._min_chars > 0 and char_count < self._min_chars:
            violations.append(
                PolicyViolation(
                    type=ViolationType.CUSTOM,
                    message=f"Content below min chars ({char_count} < {self._min_chars})",
                    severity=0.3,
                    metadata={"char_count": char_count, "minimum": self._min_chars},
                )
            )

        return GuardrailResult(
            passed=len(violations) == 0,
            violations=violations,
            metadata={"char_count": char_count, "token_count": token_count},
        )


class GuardrailStage:
    """Stage that runs multiple guardrail checks on input content.

    Combines multiple GuardrailCheck implementations and aggregates results.
    Can be configured to fail the pipeline or just log violations.

    Output data:
        - guardrail_passed: Whether all checks passed
        - violations: List of violations found
        - transformed_content: Content after transformations (if any)
        - checks_run: Number of checks executed
    """

    name = "guardrail"
    kind = StageKind.GUARD

    def __init__(
        self,
        checks: list[GuardrailCheck],
        config: GuardrailConfig | None = None,
        *,
        content_key: str | None = None,
    ) -> None:
        """Initialize guardrail stage.

        Args:
            checks: List of guardrail checks to run.
            config: Configuration for guardrail behavior.
            content_key: Key to get content from inputs (default: use snapshot.input_text).
        """
        self._checks = checks
        self._config = config or GuardrailConfig()
        self._content_key = content_key

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Run all guardrail checks."""
        # Get content to check
        if self._content_key and ctx.inputs:
            content = ctx.inputs.get(self._content_key)
        else:
            content = ctx.snapshot.input_text

        if not content:
            return StageOutput.skip(reason="No content to check")

        all_violations: list[PolicyViolation] = []
        transformed = content
        check_metadata: list[dict[str, Any]] = []

        # Run all checks
        for check in self._checks:
            check_ctx = {
                "user_id": str(ctx.snapshot.user_id) if ctx.snapshot.user_id else None,
                "session_id": str(ctx.snapshot.session_id) if ctx.snapshot.session_id else None,
            }
            result = check.check(transformed, check_ctx)

            # Filter by severity threshold
            significant_violations = [
                v for v in result.violations if v.severity >= self._config.violation_threshold
            ]
            all_violations.extend(significant_violations)

            # Apply transformations
            if self._config.transform_content and result.transformed_content:
                transformed = result.transformed_content

            check_metadata.append(result.metadata)

            # Log violations if configured
            if self._config.log_violations and significant_violations and ctx.event_sink:
                ctx.event_sink.try_emit(
                    type="guardrail.violations_detected",
                    data={
                        "violations": [v.to_dict() for v in significant_violations],
                        "check": type(check).__name__,
                    },
                )

        passed = len(all_violations) == 0

        # Build output
        output_data = {
            "guardrail_passed": passed,
            "violations": [v.to_dict() for v in all_violations],
            "checks_run": len(self._checks),
        }

        if self._config.transform_content and transformed != content:
            output_data["transformed_content"] = transformed

        # Return based on config
        if not passed and self._config.fail_on_violation:
            return StageOutput.fail(
                error=f"Guardrail violations: {len(all_violations)} found",
                data=output_data,
            )

        if not passed and not self._config.fail_on_violation:
            self._emit_fail_open_audit(ctx, all_violations)

        return StageOutput.ok(**output_data)

    def _emit_fail_open_audit(
        self,
        ctx: StageContext,
        violations: list[PolicyViolation],
    ) -> None:
        """Emit mandatory audit logging when configured to fail-open."""

        audit_payload = {
            "stage": ctx.stage_name,
            "pipeline_run_id": str(ctx.pipeline_run_id) if ctx.pipeline_run_id else None,
            "request_id": str(ctx.request_id) if ctx.request_id else None,
            "execution_mode": ctx.execution_mode,
            "violation_count": len(violations),
            "fail_on_violation": False,
            "violations": [v.to_dict() for v in violations],
        }

        if ctx.event_sink is not None:
            try:
                ctx.event_sink.try_emit(type="guardrail.fail_open", data=audit_payload)
                return
            except Exception as error:  # pragma: no cover - defensive logging
                logger.warning(
                    "Failed to emit guardrail fail-open audit", extra={"error": str(error)}
                )

        logger.warning(
            "Guardrail fail-open audit", extra={"guardrail_fail_open": audit_payload}
        )


__all__ = [
    "ContentFilter",
    "ContentLengthCheck",
    "GuardrailCheck",
    "GuardrailConfig",
    "GuardrailResult",
    "GuardrailStage",
    "InjectionDetector",
    "PIIDetector",
    "PolicyViolation",
    "ViolationType",
]
