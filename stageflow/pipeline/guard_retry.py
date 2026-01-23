"""Guard retry strategy utilities for UnifiedStageGraph."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from stageflow.core import StageKind, StageOutput


@dataclass(slots=True)
class GuardRetryPolicy:
    """Policy describing how to retry when a guard stage fails."""

    retry_stage: str
    max_attempts: int = 2
    stagnation_limit: int = 2
    hash_fields: tuple[str, ...] | None = None
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.stagnation_limit < 1:
            raise ValueError("stagnation_limit must be >= 1")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive when provided")


@dataclass(slots=True)
class GuardRetryStrategy:
    """Collection of guard retry policies keyed by guard stage name."""

    policies: dict[str, GuardRetryPolicy] = field(default_factory=dict)

    def get_policy(self, guard_stage: str) -> GuardRetryPolicy | None:
        return self.policies.get(guard_stage)

    def validate(self, stages: Mapping[str, object]) -> None:
        for guard_name, policy in self.policies.items():
            guard_spec = stages.get(guard_name)
            retry_spec = stages.get(policy.retry_stage)

            if guard_spec is None:
                raise ValueError(
                    f"Guard retry policy references unknown guard stage '{guard_name}'"
                )
            if getattr(guard_spec, "kind", None) != StageKind.GUARD:
                raise ValueError(
                    f"Guard retry policy requires '{guard_name}' to be a GUARD stage"
                )
            if retry_spec is None:
                raise ValueError(
                    f"Guard retry policy for '{guard_name}' references unknown"
                    f" retry stage '{policy.retry_stage}'"
                )
            if policy.retry_stage == guard_name:
                raise ValueError(
                    f"Guard retry policy for '{guard_name}' cannot target itself"
                )
            guard_deps = getattr(guard_spec, "dependencies", ()) or ()
            if policy.retry_stage not in guard_deps:
                raise ValueError(
                    f"Guard '{guard_name}' must declare retry stage '{policy.retry_stage}'"
                    " as a dependency to enable guard retries"
                )


def hash_retry_payload(
    output: StageOutput | None,
    fields: tuple[str, ...] | None = None,
) -> str | None:
    """Build a stable hash for stagnation detection."""

    if output is None:
        return None

    payload = output.data
    if fields:
        payload = {field: payload.get(field) for field in fields}

    try:
        serialized = json.dumps(payload, sort_keys=True, default=str)
    except TypeError:
        serialized = repr(payload)

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


__all__ = ["GuardRetryPolicy", "GuardRetryStrategy", "hash_retry_payload"]
