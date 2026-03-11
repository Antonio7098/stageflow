"""Versioned prompt templates for agent runtimes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


class PromptRenderError(ValueError):
    """Raised when a prompt cannot be rendered safely."""


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """A fully-rendered prompt with version metadata."""

    name: str
    version: str
    content: str
    variables: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """A named versioned prompt template."""

    name: str
    version: str
    template: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def render(self, variables: Mapping[str, Any] | None = None) -> RenderedPrompt:
        """Render the prompt with the provided variables."""
        provided = dict(variables or {})
        try:
            content = self.template.format_map(provided)
        except KeyError as exc:
            missing = exc.args[0]
            raise PromptRenderError(
                f"Missing prompt variable {missing!r} for {self.name}@{self.version}"
            ) from exc

        return RenderedPrompt(
            name=self.name,
            version=self.version,
            content=content,
            variables=provided,
            metadata=dict(self.metadata),
        )


class PromptLibrary:
    """Registry of versioned prompt templates."""

    def __init__(self) -> None:
        self._prompts: dict[str, dict[str, PromptTemplate]] = {}
        self._defaults: dict[str, str] = {}

    def register(self, prompt: PromptTemplate, *, make_default: bool = False) -> None:
        """Register a prompt template."""
        versions = self._prompts.setdefault(prompt.name, {})
        versions[prompt.version] = prompt
        if make_default or prompt.name not in self._defaults:
            self._defaults[prompt.name] = prompt.version

    def get(self, name: str, *, version: str | None = None) -> PromptTemplate:
        """Get a prompt by name and optional version."""
        versions = self._prompts.get(name)
        if not versions:
            raise KeyError(f"Unknown prompt: {name}")

        resolved_version = version or self._defaults.get(name)
        if resolved_version is None or resolved_version not in versions:
            raise KeyError(f"Unknown prompt version for {name}: {resolved_version!r}")
        return versions[resolved_version]

    def render(
        self,
        name: str,
        *,
        version: str | None = None,
        variables: Mapping[str, Any] | None = None,
    ) -> RenderedPrompt:
        """Render a prompt template by name."""
        return self.get(name, version=version).render(variables)

    def versions(self, name: str) -> tuple[str, ...]:
        """List all registered versions for a prompt name."""
        versions = self._prompts.get(name)
        if not versions:
            return ()
        return tuple(versions.keys())

    def list_prompts(self) -> dict[str, tuple[str, ...]]:
        """Return all prompt names and their versions."""
        return {name: tuple(versions.keys()) for name, versions in self._prompts.items()}


__all__ = [
    "PromptLibrary",
    "PromptRenderError",
    "PromptTemplate",
    "RenderedPrompt",
]
