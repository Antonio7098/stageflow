"""Extension system for stageflow.

This module provides a generic extension system for applications to add
application-specific data to ContextSnapshot without modifying core types.

Usage:
    # In your application, define an extension
    from dataclasses import dataclass, field
    from stageflow.extensions import TypedExtension

    @dataclass
    class SkillsExtension:
        active_skill_ids: list[str] = field(default_factory=list)
        current_level: str | None = None

        @property
        def key(self) -> str:
            return "skills"

        def to_dict(self) -> dict[str, Any]:
            return {
                "active_skill_ids": self.active_skill_ids,
                "current_level": self.current_level,
            }

        @classmethod
        def from_dict(cls, data: dict[str, Any]) -> "SkillsExtension":
            return cls(
                active_skill_ids=data.get("active_skill_ids", []),
                current_level=data.get("current_level"),
            )

    # Register the extension
    ExtensionRegistry.register("skills", SkillsExtension)

    # In ContextSnapshot, use extensions dict
    snapshot = ContextSnapshot(
        ...
        extensions={"skills": {"active_skill_ids": ["python"], "current_level": "intermediate"}}
    )

    # Retrieve typed extension
    skills = ExtensionHelper.get(snapshot.extensions, "skills", SkillsExtension)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

if TYPE_CHECKING:
    pass


T = TypeVar("T")


class TypedExtension(Protocol[T]):
    """Protocol for type-safe context extensions.

    Applications can implement this protocol to define type-safe extensions.
    """

    @property
    def key(self) -> str:
        """Unique key for this extension type."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Serialize extension to dict."""
        ...


class ExtensionRegistry:
    """Registry for application-specific extensions.

    This registry allows applications to register extension types that can be
    used with ExtensionHelper.get().
    """

    _extensions: dict[str, type] = {}

    @classmethod
    def register(cls, key: str, extension_type: type) -> None:
        """Register an extension type.

        Args:
            key: Unique key for this extension
            extension_type: Type class that implements the extension
        """
        cls._extensions[key] = extension_type

    @classmethod
    def get(cls, key: str) -> type | None:
        """Get an extension type by key.

        Args:
            key: The extension key

        Returns:
            The registered extension type, or None if not found
        """
        return cls._extensions.get(key)

    @classmethod
    def clear(cls) -> None:
        """Clear all registered extensions.

        Useful for testing.
        """
        cls._extensions.clear()


class ExtensionHelper:
    """Helper for working with extensions."""

    @staticmethod
    def get(data: dict[str, Any], key: str, ext_type: type[T]) -> T | None:
        """Get a typed extension from extension data.

        Args:
            data: The extensions dict from ContextSnapshot
            key: The extension key
            ext_type: The expected extension type

        Returns:
            The extension instance, or None if not found
        """
        ext_data = data.get(key)
        if ext_data is None:
            return None
        if isinstance(ext_data, dict):
            # Check if the type has a from_dict classmethod
            if hasattr(ext_type, "from_dict"):
                return ext_type.from_dict(ext_data)
            # Otherwise, try to construct from dict
            return ext_type(**ext_data)
        return ext_data


def create_skills_extension(
    active_skill_ids: list[str] | None = None,
    current_level: str | None = None,
    skill_progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Helper to create a skills extension dict.

    This is an example of how applications can structure their extensions.
    """
    return {
        "active_skill_ids": active_skill_ids or [],
        "current_level": current_level,
        "skill_progress": skill_progress or {},
    }


__all__ = [
    "ExtensionRegistry",
    "ExtensionHelper",
    "TypedExtension",
    "create_skills_extension",
]
