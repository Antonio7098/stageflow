"""Enrichment classes for the context package.

This module provides enrichment dataclasses that contain domain-specific
context data gathered during pipeline execution, such as user profiles,
memory/conversation history, and documents.

The Enrichments class groups all enrichment types into a single optional
bundle that can be attached to a ContextSnapshot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

logger = logging.getLogger("stageflow.context.enrichments")


logger = logging.getLogger("stageflow.context.enrichments")


@dataclass(frozen=True, slots=True)
class ProfileEnrichment:
    """User profile enrichment data.

    Contains user-specific context like preferences and goals
    that help personalize the pipeline execution.

    Attributes:
        user_id: The user's unique identifier.
        display_name: User's display name for personalization.
        preferences: Key-value preferences (e.g., {"theme": "dark"}).
        goals: List of user goals for coaching/learning contexts.
    """

    user_id: UUID | None = None
    display_name: str | None = None
    preferences: dict[str, Any] = field(default_factory=dict)
    goals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "user_id": str(self.user_id) if self.user_id else None,
            "display_name": self.display_name,
            "preferences": self.preferences,
            "goals": self.goals,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProfileEnrichment:
        """Create from dictionary."""
        return cls(
            user_id=UUID(data["user_id"]) if data.get("user_id") else None,
            display_name=data.get("display_name"),
            preferences=data.get("preferences", {}),
            goals=data.get("goals", []),
        )


@dataclass(frozen=True, slots=True, init=False)
class MemoryEnrichment:
    """Canonical memory view enrichment data.

    Contains conversation/interaction memory that provides context
    from previous interactions with the user.

    Attributes:
        recent_topics: Topics discussed in recent interactions.
        key_facts: Important facts learned about the user.
        interaction_history_summary: Natural language summary of history.
    """

    recent_topics: list[str] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)
    interaction_history_summary: str | None = None

    def __init__(
        self,
        *,
        recent_topics: list[str] | None = None,
        key_facts: list[str] | None = None,
        interaction_history_summary: str | None = None,
        short_term: list[str] | None = None,
        long_term: list[str] | None = None,
        summary: str | None = None,
        **extra: Any,
    ) -> None:
        """Allow legacy argument names while keeping the dataclass frozen."""

        if extra:
            unexpected = ", ".join(sorted(extra.keys()))
            raise TypeError(f"Unexpected MemoryEnrichment arguments: {unexpected}")

        if short_term is not None and recent_topics is None:
            logger.warning(
                "MemoryEnrichment.short_term is deprecated; use recent_topics instead"
            )
            recent_topics = short_term

        if long_term is not None and key_facts is None:
            logger.warning(
                "MemoryEnrichment.long_term is deprecated; use key_facts instead"
            )
            key_facts = long_term

        if summary is not None and interaction_history_summary is None:
            logger.warning(
                "MemoryEnrichment.summary is deprecated; use interaction_history_summary instead"
            )
            interaction_history_summary = summary

        object.__setattr__(self, "recent_topics", list(recent_topics or []))
        object.__setattr__(self, "key_facts", list(key_facts or []))
        object.__setattr__(
            self,
            "interaction_history_summary",
            interaction_history_summary,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "recent_topics": self.recent_topics,
            "key_facts": self.key_facts,
            "interaction_history_summary": self.interaction_history_summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEnrichment:
        """Create from dictionary."""
        return cls(
            recent_topics=data.get("recent_topics", []),
            key_facts=data.get("key_facts", []),
            interaction_history_summary=data.get("interaction_history_summary"),
        )


@dataclass(frozen=True, slots=True, init=False)
class DocumentEnrichment:
    """Document context enrichment data.

    Contains document content and metadata when the pipeline
    is processing or referencing a document.

    Attributes:
        document_id: Unique identifier for the document.
        document_type: Type of document (e.g., "pdf", "markdown").
        blocks: Structured content blocks from the document.
        metadata: Additional document metadata.
    """

    document_id: str | None = None
    document_type: str | None = None
    blocks: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        *,
        document_id: str | None = None,
        document_type: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        doc_id: str | None = None,
        doc_type: str | None = None,
        documents: list[dict[str, Any]] | None = None,
        content: str | None = None,
        **extra: Any,
    ) -> None:
        if extra:
            unexpected = ", ".join(sorted(extra.keys()))
            raise TypeError(f"Unexpected DocumentEnrichment arguments: {unexpected}")

        if doc_id is not None and document_id is None:
            logger.warning(
                "DocumentEnrichment.doc_id is deprecated; use document_id instead"
            )
            document_id = doc_id

        if doc_type is not None and document_type is None:
            logger.warning(
                "DocumentEnrichment.doc_type is deprecated; use document_type instead"
            )
            document_type = doc_type

        resolved_blocks = blocks
        resolved_metadata = metadata or {}

        if documents:
            logger.warning(
                "Passing 'documents' to DocumentEnrichment is deprecated; pass a single document via keyword arguments"
            )
            first = documents[0]
            document_id = document_id or first.get("id") or first.get("document_id")
            document_type = document_type or first.get("document_type")
            resolved_blocks = resolved_blocks or first.get("blocks")
            if resolved_blocks is None and "content" in first:
                resolved_blocks = [
                    {"type": "text", "content": first["content"]},
                ]
            resolved_metadata = {**resolved_metadata, **first.get("metadata", {})}

        if content is not None and resolved_blocks is None:
            logger.warning(
                "DocumentEnrichment.content is deprecated; provide structured blocks instead"
            )
            resolved_blocks = [{"type": "text", "content": content}]

        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "document_type", document_type)
        object.__setattr__(self, "blocks", list(resolved_blocks or []))
        object.__setattr__(self, "metadata", dict(resolved_metadata))

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "document_id": self.document_id,
            "document_type": self.document_type,
            "blocks": self.blocks,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocumentEnrichment:
        """Create from dictionary."""
        return cls(
            document_id=data.get("document_id"),
            document_type=data.get("document_type"),
            blocks=data.get("blocks", []),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True, slots=True)
class Enrichments:
    """Grouped enrichment data bundle.

    Combines all enrichment types into a single optional bundle.
    When a ContextSnapshot has enrichments=None, it means no
    enrichment has been performed yet.

    Attributes:
        profile: User profile enrichment (preferences, goals).
        memory: Memory/history enrichment (topics, facts).
        documents: List of document enrichments.
        web_results: Web search results if web enrichment was done.

    Example:
        enrichments = Enrichments(
            profile=ProfileEnrichment(user_id=user_id, display_name="Alice"),
            memory=MemoryEnrichment(recent_topics=["Python", "testing"]),
        )
    """

    profile: ProfileEnrichment | None = None
    memory: MemoryEnrichment | None = None
    documents: list[DocumentEnrichment] = field(default_factory=list)
    web_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "profile": self.profile.to_dict() if self.profile else None,
            "memory": self.memory.to_dict() if self.memory else None,
            "documents": [d.to_dict() for d in self.documents],
            "web_results": self.web_results,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Enrichments:
        """Create from dictionary."""
        profile = None
        if data.get("profile"):
            profile = ProfileEnrichment.from_dict(data["profile"])

        memory = None
        if data.get("memory"):
            memory = MemoryEnrichment.from_dict(data["memory"])

        documents = [
            DocumentEnrichment.from_dict(d) for d in data.get("documents", [])
        ]

        return cls(
            profile=profile,
            memory=memory,
            documents=documents,
            web_results=data.get("web_results", []),
        )

    @property
    def has_any(self) -> bool:
        """Check if any enrichment data is present."""
        return (
            self.profile is not None
            or self.memory is not None
            or len(self.documents) > 0
            or len(self.web_results) > 0
        )
