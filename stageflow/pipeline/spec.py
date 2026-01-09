"""Pipeline specification types for code-defined DAG composition.

This module provides the PipelineSpec dataclass and StageRunner Protocol
for defining pipeline stages with typed composition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from stageflow.core import StageOutput
    from stageflow.stages.context import PipelineContext


class PipelineValidationError(Exception):
    """Raised when pipeline validation fails."""

    def __init__(self, message: str, stages: list[str] | None = None) -> None:
        super().__init__(message)
        self.stages = stages or []


class CycleDetectedError(PipelineValidationError):
    """Raised when a cycle is detected in the pipeline DAG.

    Provides detailed information about the cycle for debugging.

    Attributes:
        cycle_path: List of stage names forming the cycle (e.g., ['A', 'B', 'C', 'A'])
        stages: All stages involved in cycles
    """

    def __init__(self, cycle_path: list[str], stages: list[str] | None = None) -> None:
        self.cycle_path = cycle_path
        cycle_str = " -> ".join(cycle_path)
        message = f"Pipeline contains a cycle: {cycle_str}"
        super().__init__(message, stages=stages or cycle_path)

    def __repr__(self) -> str:
        return f"CycleDetectedError(cycle_path={self.cycle_path})"


@runtime_checkable
class StageRunner(Protocol):
    """Protocol for stage runners.

    Any class implementing an async execute method that takes a PipelineContext
    and returns a StageOutput can be used as a StageRunner.
    """

    async def execute(self, ctx: PipelineContext) -> StageOutput:
        """Execute the stage logic.

        Args:
            ctx: Pipeline execution context with data and metadata

        Returns:
            StageOutput with status and optional data/error
        """
        ...


@dataclass(frozen=True, slots=True)
class PipelineSpec:
    """Specification for a pipeline stage.

    Immutable specification that defines a stage's runner, dependencies,
    inputs/outputs, and conditional execution flag.

    Attributes:
        name: Unique stage name within the pipeline
        runner: Stage class or instance implementing StageRunner protocol
        dependencies: Names of stages that must complete before this one
        inputs: Keys this stage reads from the context
        outputs: Keys this stage writes to the context
        conditional: If True, stage may be skipped based on context
        args: Additional arguments passed to the stage runner
    """

    name: str
    runner: type[StageRunner] | StageRunner
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    inputs: tuple[str, ...] = field(default_factory=tuple)
    outputs: tuple[str, ...] = field(default_factory=tuple)
    conditional: bool = False
    args: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the spec after initialization."""
        if not self.name:
            raise ValueError("PipelineSpec name cannot be empty")
        if not self.name.strip():
            raise ValueError("PipelineSpec name cannot be whitespace-only")
        if self.name in self.dependencies:
            raise ValueError(
                f"PipelineSpec '{self.name}' cannot depend on itself"
            )

    def __hash__(self) -> int:
        """Make PipelineSpec hashable for use in sets/dicts."""
        return hash((
            self.name,
            id(self.runner),
            self.dependencies,
            self.inputs,
            self.outputs,
            self.conditional,
        ))


__all__ = [
    "CycleDetectedError",
    "PipelineSpec",
    "PipelineValidationError",
    "StageRunner",
]
