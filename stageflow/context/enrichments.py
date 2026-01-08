"""Enrichment classes for the context package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProfileEnrichment:
    """User profile enrichment data."""

    user_id: UUID
    display_name: str | None = None
    preferences: dict[str, Any] = field(default_factory=dict)
    goals: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MemoryEnrichment:
    """Canonical memory view enrichment data."""

    recent_topics: list[str] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)
    interaction_history_summary: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentEnrichment:
    """Document context enrichment data."""

    document_id: str | None = None
    document_type: str | None = None
    blocks: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
