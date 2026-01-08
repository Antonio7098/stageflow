"""Pipeline registry for lazy registration and retrieval.

Provides a centralized registry for Pipeline instances with lazy
registration to avoid circular import issues during startup.

Usage:
    pipeline = pipeline_registry.get("chat_fast")
    names = pipeline_registry.list()
"""

from __future__ import annotations

from .pipeline import Pipeline


class PipelineRegistry:
    """Simple mapping of names to Pipeline instances with lazy registration.

    Implements lazy registration pattern where pipelines are only
    registered when first accessed, avoiding circular imports during
    module initialization.
    """

    def __init__(self) -> None:
        self._pipelines: dict[str, Pipeline] = {}
        self._registered = False

    def get(self, name: str) -> Pipeline:
        """Get a pipeline by name (auto-registers on first access).

        Args:
            name: Pipeline name to retrieve

        Returns:
            Pipeline instance

        Raises:
            KeyError: If pipeline name is not found
        """
        if not self._registered:
            self._register_all()

        if name not in self._pipelines:
            raise KeyError(
                f"Pipeline '{name}' not found. Available: {list(self._pipelines.keys())}"
            )

        return self._pipelines[name]

    def list(self) -> list[str]:
        """List all registered pipeline names."""
        if not self._registered:
            self._register_all()
        return list(self._pipelines.keys())

    def _register_all(self) -> None:
        """Register all pipelines (called lazily on first access).

        Override this method or call register() to add pipelines.
        """
        if self._registered:
            return
        self._registered = True

    def register(self, name: str, pipeline: Pipeline) -> None:
        """Register a pipeline instance.

        Args:
            name: Pipeline name
            pipeline: Pipeline instance to register
        """
        self._pipelines[name] = pipeline

    def __contains__(self, name: str) -> bool:
        """Check if pipeline name is registered."""
        if not self._registered:
            self._register_all()
        return name in self._pipelines


# Global registry instance
pipeline_registry = PipelineRegistry()


__all__ = [
    "PipelineRegistry",
    "pipeline_registry",
]
