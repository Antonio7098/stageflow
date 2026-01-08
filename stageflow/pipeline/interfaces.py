"""Stage interfaces for ISP (Interface Segregation Principle).

This module defines minimal interfaces for different stage capabilities,
allowing stages to implement only what they need.

Interfaces:
- Stage: Base minimal interface (name + run)
- DependentStage: For stages requiring injected dependencies
- RetryableStage: For stages that can be retried on failure
- ConditionalStage: For stages that can be conditionally skipped
- ObservableStage: For stages that emit events during execution

Usage:
    class MyStage(Stage, RetryableStage):
        name = "my_stage"
        max_retries = 3

        async def run(self, ctx: PipelineContext) -> StageResult:
            ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import PipelineContext, StageResult


class Stage(ABC):
    """Minimal stage interface.

    All pipeline stages must implement this interface.
    Provides only the essential contract: name and run method.
    """

    name: str

    @abstractmethod
    async def run(self, ctx: PipelineContext) -> StageResult:  # pragma: no cover - interface
        """Execute the stage logic.

        Args:
            ctx: Pipeline context containing shared data and state

        Returns:
            StageResult indicating success, failure, or other status
        """
        ...


class DependentStage(ABC):
    """Interface for stages that require external dependencies.

    Use this for stages that need services, ports, or other dependencies
    injected during initialization.
    """

    @abstractmethod
    def __init__(self, *args, **kwargs) -> None:
        """Initialize stage with required dependencies.

        Concrete classes should define their specific dependency types.
        """
        ...


class RetryableStage(ABC):
    """Interface for stages that support retry on failure.

    Use this for stages that can safely retry after transient failures
    (network errors, timeouts, etc.).
    """

    max_retries: int = 0
    """Maximum number of retry attempts (default: 0, no retries)."""

    retryable_errors: tuple[type, ...] = ()
    """Tuple of error types that are retryable."""

    @abstractmethod
    async def run(self, ctx: PipelineContext) -> StageResult:  # pragma: no cover - interface
        """Execute the stage with retry support.

        The orchestrator will handle retry logic based on max_retries
        and retryable_errors.
        """
        ...

    def should_retry(self, error: Exception) -> bool:
        """Determine if an error is retryable.

        Args:
            error: The exception that caused the failure

        Returns:
            True if the error is retryable
        """
        return isinstance(error, self.retryable_errors) if self.retryable_errors else False


class ConditionalStage(ABC):
    """Interface for stages that can be conditionally skipped.

    Use this for stages that should only run based on certain conditions
    (e.g., triage decisions, feature flags).
    """

    @abstractmethod
    async def run(self, ctx: PipelineContext) -> StageResult:  # pragma: no cover - interface
        """Execute the stage or skip based on condition.

        The orchestrator will check should_run() before execution.
        """
        ...

    @abstractmethod
    def should_run(self, ctx: PipelineContext) -> bool:
        """Determine if this stage should execute.

        Args:
            ctx: Pipeline context with decision-making data

        Returns:
            True if the stage should run, False to skip
        """
        ...


class ObservableStage(ABC):
    """Interface for stages that emit detailed events.

    Use this for stages that need to emit events beyond basic
    started/completed/failed lifecycle events.
    """

    @abstractmethod
    async def run(self, ctx: PipelineContext) -> StageResult:  # pragma: no cover - interface
        """Execute the stage with event emission.

        Concrete implementations should emit events during execution
        using ctx.record_stage_event() or other event mechanisms.
        """
        ...


class ConfigurableStage(ABC):
    """Interface for stages with runtime configuration.

    Use this for stages whose behavior can be configured at runtime
    (e.g., via pipeline configuration, feature flags).
    """

    @abstractmethod
    def configure(self, config: dict) -> None:
        """Apply runtime configuration to the stage.

        Args:
            config: Configuration dictionary
        """
        ...

    @abstractmethod
    def get_config(self) -> dict:
        """Get the current stage configuration.

        Returns:
            Current configuration dictionary
        """
        ...


# Re-export for convenience
__all__ = [
    "Stage",
    "DependentStage",
    "RetryableStage",
    "ConditionalStage",
    "ObservableStage",
    "ConfigurableStage",
]
