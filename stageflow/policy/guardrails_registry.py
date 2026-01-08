"""Guardrails registry for self-registration of content moderation strategies.

This module provides a registry pattern that allows guardrails implementations
to self-register, enabling pluggable content moderation strategies.

Usage:
    # In guardrails module - self-register
    from app.ai.framework.policy.guardrails_registry import register_guardrails, get_guardrails

    @register_guardrails(name="content_moderation", checkpoints=["pre_llm", "pre_action"])
    class ContentModerationGuardrails:
        async def evaluate(self, checkpoint, context):
            ...

    # In policy stage - lookup guardrails by checkpoint
    from app.ai.framework.policy.guardrails_registry import get_guardrails_by_checkpoint

    guardrails = get_guardrails_by_checkpoint("pre_llm")
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class GuardrailsRegistration:
    """Registration information for a single guardrails implementation.

    Guardrails are content moderation strategies that can run at different
    checkpoints in the pipeline (pre_llm, pre_action, pre_persist).
    """

    name: str  # Guardrails identifier (e.g., "content_moderation", "pII_detection")
    guardrails_class: type  # The guardrails class
    checkpoints: tuple[
        str, ...
    ]  # Checkpoints where this runs: "pre_llm", "pre_action", "pre_persist"
    description: str = ""  # Human-readable description


class GuardrailsRegistry:
    """Central registry for guardrails implementations.

    This is a project-level singleton. Concrete projects (like
    Eloquence) register their own guardrails. Substrate only
    provides the registration mechanism.
    """

    _registry: dict[str, GuardrailsRegistration] = {}

    @classmethod
    def register(
        cls,
        name: str,
        *,
        checkpoints: list[str] | None = None,
        description: str = "",
    ) -> Callable[[type], type]:
        """Decorator to register a guardrails class.

        Args:
            name: Unique identifier for the guardrails (e.g., "content_moderation")
            checkpoints: List of checkpoints where this guardrails runs
            description: Human-readable description of the guardrails

        Returns:
            Decorator that registers the guardrails class

        Raises:
            ValueError: If guardrails with this name is already registered
        """

        def decorator(guardrails_class: type) -> type:
            if name in cls._registry:
                existing = cls._registry[name]
                raise ValueError(
                    f"Guardrails '{name}' is already registered to class '{existing.guardrails_class.__name__}'. "
                    f"Cannot re-register to '{guardrails_class.__name__}'."
                )

            cls._registry[name] = GuardrailsRegistration(
                name=name,
                guardrails_class=guardrails_class,
                checkpoints=tuple(checkpoints) if checkpoints else (),
                description=description,
            )

            return guardrails_class

        return decorator

    @classmethod
    def get(cls, name: str) -> type | None:
        """Get a guardrails class by name.

        Args:
            name: The guardrails identifier

        Returns:
            The guardrails class or None if not found
        """
        registration = cls._registry.get(name)
        return registration.guardrails_class if registration else None

    @classmethod
    def get_or_raise(cls, name: str) -> type:
        """Get a guardrails class by name, raising if not found.

        Args:
            name: The guardrails identifier

        Returns:
            The guardrails class

        Raises:
            KeyError: If guardrails is not registered
        """
        registration = cls._registry.get(name)
        if registration is None:
            available = cls.list()
            raise KeyError(
                f"Guardrails '{name}' not found in registry. Available guardrails: {available}"
            )
        return registration.guardrails_class

    @classmethod
    def get_registration(cls, name: str) -> GuardrailsRegistration | None:
        """Get the full registration for a guardrails.

        Args:
            name: The guardrails identifier

        Returns:
            GuardrailsRegistration or None if not found
        """
        return cls._registry.get(name)

    @classmethod
    def list(cls) -> list[str]:
        """List all registered guardrails names.

        Returns:
            List of guardrails identifiers
        """
        return list(cls._registry.keys())

    @classmethod
    def list_with_details(cls) -> list[dict[str, str | tuple[str, ...]]]:
        """List all guardrails with their details.

        Returns:
            List of dicts with name, checkpoints, and description
        """
        return [
            {
                "name": reg.name,
                "checkpoints": reg.checkpoints,
                "description": reg.description,
            }
            for reg in cls._registry.values()
        ]

    @classmethod
    def get_by_checkpoint(cls, checkpoint: str) -> list[type]:
        """Get all guardrails that handle a specific checkpoint.

        Args:
            checkpoint: The checkpoint type ("pre_llm", "pre_action", "pre_persist")

        Returns:
            List of guardrails classes that handle this checkpoint
        """
        return [
            reg.guardrails_class for reg in cls._registry.values() if checkpoint in reg.checkpoints
        ]

    @classmethod
    def get_all(cls) -> dict[str, GuardrailsRegistration]:
        """Get all registrations.

        Returns:
            Dictionary mapping guardrails name to registration
        """
        return cls._registry.copy()

    @classmethod
    def has(cls, name: str) -> bool:
        """Check if a guardrails is registered.

        Args:
            name: The guardrails identifier

        Returns:
            True if registered, False otherwise
        """
        return name in cls._registry

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations.

        WARNING: This is primarily for testing. Do not call
        in production unless you know what you're doing.
        """
        cls._registry.clear()

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a guardrails from the registry.

        Args:
            name: The guardrails identifier to remove

        Raises:
            KeyError: If guardrails is not registered
        """
        if name not in cls._registry:
            raise KeyError(f"Guardrails '{name}' is not registered")
        del cls._registry[name]


guardrails_registry = GuardrailsRegistry()


def register_guardrails(
    name: str | None = None,
    *,
    checkpoints: list[str] | None = None,
    description: str = "",
) -> Callable[[type], type]:
    """Convenience decorator to register a guardrails class.

    Args:
        name: Optional guardrails identifier (defaults to class name)
        checkpoints: Checkpoints where this guardrails runs
        description: Human-readable description

    Returns:
        Decorator that registers the guardrails class

    Usage:
        @register_guardrails(
            name="content_moderation",
            checkpoints=["pre_llm", "pre_action"],
            description="Content moderation guardrails"
        )
        class ContentModerationGuardrails:
            async def evaluate(self, checkpoint, context):
                ...
    """
    actual_name = name

    def decorator(guardrails_class: type) -> type:
        guardrails_name = actual_name or guardrails_class.__name__
        return guardrails_registry.register(
            guardrails_name, checkpoints=checkpoints, description=description
        )(guardrails_class)

    return decorator


def get_guardrails(name: str) -> type | None:
    """Get a guardrails class by name.

    Args:
        name: The guardrails identifier

    Returns:
        The guardrails class or None if not found
    """
    return guardrails_registry.get(name)


def get_guardrails_or_raise(name: str) -> type:
    """Get a guardrails class by name, raising if not found.

    Args:
        name: The guardrails identifier

    Returns:
        The guardrails class

    Raises:
        KeyError: If guardrails is not registered
    """
    return guardrails_registry.get_or_raise(name)


def list_guardrails() -> list[str]:
    """List all registered guardrails names.

    Returns:
        List of guardrails identifiers
    """
    return guardrails_registry.list()


def list_guardrails_with_details() -> list[dict[str, str | tuple[str, ...]]]:
    """List all guardrails with their details.

    Returns:
        List of dicts with name, checkpoints, and description
    """
    return guardrails_registry.list_with_details()


def get_guardrails_by_checkpoint(checkpoint: str) -> list[type]:
    """Get all guardrails that handle a specific checkpoint.

    Args:
        checkpoint: The checkpoint type

    Returns:
        List of guardrails classes that handle this checkpoint
    """
    return guardrails_registry.get_by_checkpoint(checkpoint)


def clear_guardrails_registry() -> None:
    """Clear all guardrails registrations.

    WARNING: This is primarily for testing.
    """
    guardrails_registry.clear()


__all__ = [
    "GuardrailsRegistration",
    "GuardrailsRegistry",
    "guardrails_registry",
    "register_guardrails",
    "get_guardrails",
    "get_guardrails_or_raise",
    "list_guardrails",
    "list_guardrails_with_details",
    "get_guardrails_by_checkpoint",
    "clear_guardrails_registry",
]
