"""StageInputs - Immutable view of prior stage outputs available to a stage.

This module defines StageInputs, an immutable dataclass that provides stages with
access to the original ContextSnapshot and outputs from declared dependency stages.
This replaces the mutable shared state pattern (ctx.config["data"]).

Key Principles:
- Immutable: frozen=True prevents accidental mutation
- Explicit: Only declared dependency outputs are accessible
- Validated: Strict mode raises errors for undeclared dependencies
- Typed: StageOutput is already a frozen dataclass with typed fields

Example:
    # Stage receives StageInputs in its context
    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs: StageInputs = ctx.inputs

        # From original snapshot
        user_id = inputs.snapshot.user_id

        # From specific prior stage (strict - only declared deps)
        transcript = inputs.get_from("stt_stage", "transcript")

        # Search all prior outputs for a key
        transcript = inputs.get("transcript")

        # Services through ports (typed, explicit)
        await inputs.ports.send_status("stt", "started", None)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from stageflow.core import StageOutput
from stageflow.stages.ports import AudioPorts, CorePorts, LLMPorts

if TYPE_CHECKING:
    from stageflow.context import ContextSnapshot


class UndeclaredDependencyError(Exception):
    """Raised when a stage accesses an undeclared dependency.

    This error enforces explicit dependency contracts between stages.
    To fix, add the dependency to the stage's depends_on list in the
    pipeline configuration.

    Attributes:
        stage_name: The undeclared dependency that was accessed.
        declared_deps: The set of declared dependencies.
        accessing_stage: The stage that tried to access the dependency.
    """

    def __init__(
        self,
        stage_name: str,
        declared_deps: frozenset[str],
        accessing_stage: str | None = None,
    ) -> None:
        self.stage_name = stage_name
        self.declared_deps = declared_deps
        self.accessing_stage = accessing_stage

        deps_list = sorted(declared_deps) if declared_deps else ["(none)"]
        msg = (
            f"Attempted to access undeclared dependency '{stage_name}'. "
            f"Declared dependencies: {deps_list}. "
            f"Add '{stage_name}' to depends_on to fix this error."
        )
        if accessing_stage:
            msg = f"Stage '{accessing_stage}': {msg}"
        super().__init__(msg)


@dataclass(frozen=True, slots=True)
class StageInputs:
    """Immutable view of prior stage outputs available to a stage.

    This is the canonical input type for stages that follow the immutable
    data flow pattern. It provides:

    1. snapshot: The original immutable ContextSnapshot with run identity,
       messages, enrichments, and routing decision.

    2. prior_outputs: A dict of StageOutput from declared dependency stages.
       Only stages that are explicitly declared as dependencies will appear
       here. This enforces explicit contracts between stages.

    3. ports: Injected capabilities (db, callbacks, services) for the stage.

    4. declared_deps: Frozenset of declared dependency stage names. Used for
       strict validation mode.

    5. stage_name: Name of the stage receiving these inputs (for error messages).

    Attributes:
        snapshot: Original immutable snapshot (run identity, messages, etc.)
        prior_outputs: Outputs from declared dependency stages only.
        ports: Injected capabilities (db, callbacks, services).
        declared_deps: Set of declared dependencies (for validation).
        stage_name: Name of the receiving stage (for error messages).
        strict: If True, raises UndeclaredDependencyError for undeclared access.
    """

    snapshot: ContextSnapshot
    prior_outputs: dict[str, StageOutput] = field(default_factory=dict)
    ports: CorePorts | LLMPorts | AudioPorts | None = field(default_factory=lambda: None)
    declared_deps: frozenset[str] = field(default_factory=frozenset)
    stage_name: str | None = None
    strict: bool = True

    def _validate_dependency(self, stage_name: str) -> None:
        """Validate that a stage is a declared dependency.

        Args:
            stage_name: The dependency stage to validate.

        Raises:
            UndeclaredDependencyError: If strict=True and stage is not declared.
        """
        if self.strict and self.declared_deps and stage_name not in self.declared_deps:
            raise UndeclaredDependencyError(
                stage_name=stage_name,
                declared_deps=self.declared_deps,
                accessing_stage=self.stage_name,
            )

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from any prior stage's output data.

        Searches through all prior_outputs in insertion order and returns
        the first value found for the given key. This is useful when you
        don't know which stage produced a value.

        Note: This method does not validate dependencies since it searches
        all outputs. Use get_from() for explicit, validated access.

        Args:
            key: The key to search for in output.data dicts.
            default: Value to return if key not found.

        Returns:
            The value from the first prior output containing the key,
            or default if not found.
        """
        for output in self.prior_outputs.values():
            if key in output.data:
                return output.data[key]
        return default

    def get_from(self, stage_name: str, key: str, default: Any = None) -> Any:
        """Get a specific value from a specific stage's output.

        This is the preferred method for accessing prior outputs because
        it makes the dependency explicit and validates against declared
        dependencies when strict=True.

        Args:
            stage_name: Name of the dependency stage.
            key: The key to look up in that stage's output.data.
            default: Value to return if stage not found or key not present.

        Returns:
            The value from the specified stage's output, or default.

        Raises:
            UndeclaredDependencyError: If strict=True and stage is not
                in declared_deps.
        """
        self._validate_dependency(stage_name)

        if stage_name not in self.prior_outputs:
            return default
        return self.prior_outputs[stage_name].data.get(key, default)

    def has_output(self, stage_name: str) -> bool:
        """Check if a stage has produced output.

        Args:
            stage_name: Name of the stage to check.

        Returns:
            True if the stage has been executed and produced output.

        Raises:
            UndeclaredDependencyError: If strict=True and stage is not
                in declared_deps.
        """
        self._validate_dependency(stage_name)
        return stage_name in self.prior_outputs

    def get_output(self, stage_name: str) -> StageOutput | None:
        """Get a stage's complete output.

        Args:
            stage_name: Name of the stage.

        Returns:
            The StageOutput if found, None otherwise.

        Raises:
            UndeclaredDependencyError: If strict=True and stage is not
                in declared_deps.
        """
        self._validate_dependency(stage_name)
        return self.prior_outputs.get(stage_name)

    def require_from(self, stage_name: str, key: str) -> Any:
        """Get a required value from a specific stage's output.

        Similar to get_from but raises KeyError if the value is not found.
        Use this when the value must exist for the stage to function.

        Args:
            stage_name: Name of the dependency stage.
            key: The key to look up in that stage's output.data.

        Returns:
            The value from the specified stage's output.

        Raises:
            UndeclaredDependencyError: If strict=True and stage is not declared.
            KeyError: If stage has no output or key is not in output.data.
        """
        self._validate_dependency(stage_name)

        if stage_name not in self.prior_outputs:
            raise KeyError(
                f"Required dependency '{stage_name}' has no output. "
                f"Ensure '{stage_name}' executes before this stage."
            )

        output = self.prior_outputs[stage_name]
        if key not in output.data:
            raise KeyError(
                f"Required key '{key}' not found in output from '{stage_name}'. "
                f"Available keys: {list(output.data.keys())}"
            )

        return output.data[key]


def create_stage_inputs(
    snapshot: ContextSnapshot,
    *,
    prior_outputs: dict[str, StageOutput] | None = None,
    ports: CorePorts | LLMPorts | AudioPorts | None = None,
    declared_deps: frozenset[str] | set[str] | list[str] | None = None,
    stage_name: str | None = None,
    strict: bool = True,
) -> StageInputs:
    """Factory function to create StageInputs.

    This is the recommended way to create StageInputs instances.

    Args:
        snapshot: The original immutable ContextSnapshot.
        prior_outputs: Dict of outputs from dependency stages.
        ports: Injected capabilities for the stage.
        declared_deps: Set of declared dependency stage names.
        stage_name: Name of the stage receiving these inputs.
        strict: If True, validates dependency access.

    Returns:
        StageInputs instance ready for use by stages.
    """
    deps: frozenset[str]
    if declared_deps is None:
        deps = frozenset()
    elif isinstance(declared_deps, frozenset):
        deps = declared_deps
    else:
        deps = frozenset(declared_deps)

    return StageInputs(
        snapshot=snapshot,
        prior_outputs=prior_outputs or {},
        ports=ports,
        declared_deps=deps,
        stage_name=stage_name,
        strict=strict,
    )


__all__ = [
    "StageInputs",
    "UndeclaredDependencyError",
    "create_stage_inputs",
]
