"""StageInputs - Immutable view of prior stage outputs available to a stage.

This module defines StageInputs, an immutable dataclass that provides stages with
access to the original ContextSnapshot and outputs from declared dependency stages.
This replaces the mutable shared state pattern (ctx.config["data"]).

Key Principles:
- Immutable: frozen=True prevents accidental mutation
- Explicit: Only declared dependency outputs are accessible
- Typed: StageOutput is already a frozen dataclass with typed fields

Example:
    # Stage receives StageInputs in its context
    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs: StageInputs = ctx.config["inputs"]

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

from stageflow.stages.ports import StagePorts

if TYPE_CHECKING:
    from stageflow.context import ContextSnapshot


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

    Attributes:
        snapshot: Original immutable snapshot (run identity, messages, etc.)
        prior_outputs: Outputs from declared dependency stages only.
        ports: Injected capabilities (db, callbacks, services).
    """

    snapshot: ContextSnapshot
    prior_outputs: dict[str, StageOutput] = field(default_factory=dict)
    ports: StagePorts = field(default_factory=StagePorts)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from any prior stage's output data.

        Searches through all prior_outputs in insertion order and returns
        the first value found for the given key. This is useful when you
        don't know which stage produced a value.

        Args:
            key: The key to search for in output.data dicts.
            default: Value to return if key not found.

        Returns:
            The value from the first prior output containing the key,
            or default if not found.
        """
        import sys
        print(f"[INPUTS_GET] get('{key}') called, prior_outputs keys: {list(self.prior_outputs.keys())}", file=sys.stderr)
        
        for output in self.prior_outputs.values():
            if key in output.data:
                result = output.data[key]
                print(f"[INPUTS_GET] Found key '{key}' in output (status={output.status}), value={repr(result)[:100]}", file=sys.stderr)
                return result
        
        print(f"[INPUTS_GET] Key '{key}' not found, returning default={repr(default)[:100]}", file=sys.stderr)
        return default

    def get_from(self, stage_name: str, key: str, default: Any = None) -> Any:
        """Get a specific value from a specific stage's output.

        This is the preferred method for accessing prior outputs because
        it makes the dependency explicit and provides type safety.

        Args:
            stage_name: Name of the dependency stage.
            key: The key to look up in that stage's output.data.
            default: Value to return if stage not found or key not present.

        Returns:
            The value from the specified stage's output, or default.
        """
        if stage_name not in self.prior_outputs:
            return default
        return self.prior_outputs[stage_name].data.get(key, default)

    def has_output(self, stage_name: str) -> bool:
        """Check if a stage has produced output.

        Args:
            stage_name: Name of the stage to check.

        Returns:
            True if the stage has been executed and produced output.
        """
        return stage_name in self.prior_outputs

    def get_output(self, stage_name: str) -> StageOutput | None:
        """Get a stage's complete output.

        Args:
            stage_name: Name of the stage.

        Returns:
            The StageOutput if found, None otherwise.
        """
        return self.prior_outputs.get(stage_name)


def create_stage_inputs(
    snapshot: ContextSnapshot,
    *,
    prior_outputs: dict[str, StageOutput] | None = None,
    ports: StagePorts | None = None,
) -> StageInputs:
    """Factory function to create StageInputs.

    This is the recommended way to create StageInputs instances.

    Args:
        snapshot: The original immutable ContextSnapshot.
        prior_outputs: Dict of outputs from dependency stages.
        ports: Injected capabilities for the stage.

    Returns:
        StageInputs instance ready for use by stages.
    """
    return StageInputs(
        snapshot=snapshot,
        prior_outputs=prior_outputs or {},
        ports=ports or StagePorts(),
    )


__all__ = [
    "StageInputs",
    "create_stage_inputs",
]
