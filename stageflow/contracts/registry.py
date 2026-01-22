"""Schema registry utilities for stage contract management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class ContractMetadata:
    """Registered metadata for a stage contract version."""

    stage: str
    version: str
    model: type[BaseModel]
    schema: dict[str, Any]
    description: str | None = None
    created_at: datetime = datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ContractCompatibilityReport:
    """Simple compatibility diff between two contract versions."""

    stage: str
    from_version: str
    to_version: str
    breaking_changes: list[str]
    warnings: list[str]

    @property
    def is_compatible(self) -> bool:
        """True when no breaking changes were detected."""

        return not self.breaking_changes

    def summary(self) -> str:
        """Human readable summary string."""

        status = "compatible" if self.is_compatible else "breaking"
        return (
            f"Contract diff for {self.stage} {self.from_version}->{self.to_version}: "
            f"{status} (breaking={len(self.breaking_changes)}, warnings={len(self.warnings)})"
        )


class ContractRegistry:
    """In-memory registry of stage contract schemas."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], ContractMetadata] = {}

    def clear(self) -> None:
        """Remove all registered entries (primarily for tests)."""

        self._entries.clear()

    def register(
        self,
        *,
        stage: str,
        version: str,
        model: type[BaseModel],
        description: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> ContractMetadata:
        """Register or update metadata for a stage/version pair."""

        key = (stage, version)
        if key in self._entries:
            existing = self._entries[key]
            if existing.model is model:
                return existing
            raise ValueError(f"Contract {stage}@{version} already registered with a different model")

        schema = schema or model.model_json_schema(mode="validation")
        metadata = ContractMetadata(
            stage=stage,
            version=version,
            model=model,
            schema=schema,
            description=description,
        )
        self._entries[key] = metadata
        return metadata

    def get(self, stage: str, version: str) -> ContractMetadata | None:
        """Fetch metadata for a given stage/version."""

        return self._entries.get((stage, version))

    def list(self, stage: str | None = None) -> list[ContractMetadata]:
        """Return all registrations, optionally filtered by stage."""

        if stage is None:
            return sorted(self._entries.values(), key=lambda m: (m.stage, m.version))
        return sorted(
            (entry for entry in self._entries.values() if entry.stage == stage),
            key=lambda m: m.version,
        )

    def diff(self, stage: str, from_version: str, to_version: str) -> ContractCompatibilityReport:
        """Compute compatibility between two versions of a stage contract."""

        left = self.get(stage, from_version)
        right = self.get(stage, to_version)
        if left is None or right is None:
            missing = from_version if left is None else to_version
            raise ValueError(f"Contract {stage}@{missing} not registered")

        breaking: list[str] = []
        warnings: list[str] = []

        left_fields = _field_map(left.schema)
        right_fields = _field_map(right.schema)

        # Removed fields -> breaking
        for field in left_fields:
            if field not in right_fields:
                breaking.append(f"Field '{field}' removed")

        # Added fields -> warning unless required
        for field, meta in right_fields.items():
            if field not in left_fields:
                if meta.required:
                    breaking.append(f"Required field '{field}' added")
                else:
                    warnings.append(f"Optional field '{field}' added")
                continue

            left_meta = left_fields[field]
            if not _types_compatible(left_meta.types, meta.types):
                breaking.append(
                    f"Field '{field}' changed types {left_meta.types} -> {meta.types}"
                )

        return ContractCompatibilityReport(
            stage=stage,
            from_version=from_version,
            to_version=to_version,
            breaking_changes=breaking,
            warnings=warnings,
        )


def _field_map(schema: dict[str, Any]) -> dict[str, _FieldInfo]:
    props: dict[str, Any] = schema.get("properties", {}) or {}
    required: set[str] = set(schema.get("required", []) or [])
    field_info: dict[str, _FieldInfo] = {}

    for name, meta in props.items():
        json_types = meta.get("type")
        if isinstance(json_types, str):
            types = {json_types}
        elif isinstance(json_types, list):
            types = set(json_types)
        else:
            types = {"object"} if "properties" in meta else set()
        field_info[name] = _FieldInfo(name=name, types=types, required=name in required)
    return field_info


@dataclass(frozen=True, slots=True)
class _FieldInfo:
    name: str
    types: set[str]
    required: bool


def _types_compatible(old: set[str], new: set[str]) -> bool:
    if not old:
        return True
    if new.issuperset(old):
        return True
    # Allow widening to include "null"
    return old == new.union({"null"})


registry = ContractRegistry()

__all__ = [
    "ContractCompatibilityReport",
    "ContractMetadata",
    "ContractRegistry",
    "registry",
]
