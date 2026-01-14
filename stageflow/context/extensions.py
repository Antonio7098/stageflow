"""ExtensionBundle - Base class for user-defined context extensions.

This module provides the ExtensionBundle base class that enables users to
define their own typed context extensions for domain-specific data.

Example:
    # Define your domain-specific extensions
    @dataclass(frozen=True)
    class SalesExtensions(ExtensionBundle):
        deal: DealInfo | None = None
        competitors: list[CompetitorMention] = field(default_factory=list)
        compliance: ComplianceContext | None = None

    # Use with typed ContextSnapshot
    snapshot: ContextSnapshot[SalesExtensions] = ContextSnapshot(
        run_id=run_id,
        extensions=SalesExtensions(deal=DealInfo(...)),
    )

    # Access with full type safety
    snapshot.extensions.deal.value  # IDE autocomplete works
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any, TypeVar

T = TypeVar("T", bound="ExtensionBundle")


@dataclass(frozen=True)
class ExtensionBundle:
    """Base class for user-defined context extensions.

    Subclass this to create typed extension bundles for domain-specific
    context data. Extension bundles must be frozen dataclasses to
    maintain immutability guarantees.

    The bundle provides serialization support via to_dict() and from_dict()
    methods that work with nested dataclasses.

    Example:
        @dataclass(frozen=True)
        class MyExtensions(ExtensionBundle):
            custom_field: str = ""
            nested_data: MyNestedType | None = None
    """

    def to_dict(self) -> dict[str, Any]:
        """Convert extension bundle to JSON-serializable dictionary.

        Handles nested dataclasses by recursively calling to_dict if available,
        or using dataclass field introspection.

        Returns:
            Dictionary representation of the extension bundle.
        """
        result: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            result[f.name] = _serialize_value(value)
        return result

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        """Create extension bundle from dictionary.

        Note: This base implementation creates the bundle with the raw
        dict values. For complex nested types, subclasses should override
        this method to handle deserialization of nested objects.

        Args:
            data: Dictionary with extension data.

        Returns:
            ExtensionBundle instance.
        """
        return cls(**data)


def _serialize_value(value: Any) -> Any:
    """Recursively serialize a value for JSON.

    Args:
        value: Any value to serialize.

    Returns:
        JSON-serializable representation.
    """
    if value is None:
        return None

    # Handle dataclasses
    if is_dataclass(value) and not isinstance(value, type):
        if hasattr(value, "to_dict"):
            return value.to_dict()
        # Fallback for dataclasses without to_dict
        result = {}
        for f in fields(value):
            result[f.name] = _serialize_value(getattr(value, f.name))
        return result

    # Handle lists
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]

    # Handle dicts
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}

    # Handle UUIDs, datetimes, etc.
    if hasattr(value, "__str__") and not isinstance(value, (str, int, float, bool)):
        # Check for common types that should be stringified
        type_name = type(value).__name__
        if type_name in ("UUID", "datetime", "date", "time"):
            return str(value)

    return value


__all__ = [
    "ExtensionBundle",
    "T",
]
