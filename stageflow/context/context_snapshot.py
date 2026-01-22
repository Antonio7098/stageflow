"""ContextSnapshot - Immutable view of execution context.

This module provides ContextSnapshot, the immutable data structure that captures
the complete state of a pipeline execution context. It supports:

1. **Composition**: Groups related data into RunIdentity, Enrichments, and Conversation
2. **Typed Extensions**: Generic[T] parameter for domain-specific extension bundles
3. **Serialization**: Full JSON roundtrip support for testing and replay
4. **Backwards Compatibility**: Properties for accessing fields in the old flat structure

ContextSnapshot is serializable to JSON to support unit testing and Central Pulse replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from stageflow.context.conversation import Conversation
from stageflow.context.enrichments import (
    DocumentEnrichment,
    Enrichments,
    MemoryEnrichment,
    ProfileEnrichment,
)
from stageflow.context.extensions import ExtensionBundle
from stageflow.context.identity import RunIdentity
from stageflow.context.types import Message, RoutingDecision

# Type variable for user-defined extensions
T = TypeVar("T", bound=ExtensionBundle)


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ContextSnapshot(Generic[T]):
    """Immutable view passed to stages containing run identity, messages, enrichments, and routing decision.

    This is the canonical input to stages and agents. It is:
    - Immutable (frozen dataclass)
    - Serializable to JSON (for testing and Central Pulse replay)
    - Complete (contains everything the stage needs)
    - Extensible (Generic[T] for domain-specific extensions)

    The structure uses composition to group related fields:
    - run_id: RunIdentity with all correlation IDs
    - enrichments: Enrichments bundle (profile, memory, documents, web)
    - conversation: Conversation bundle (messages, routing decision)
    - extensions: User-defined typed extension bundle

    All fields have sensible defaults for easy instantiation in tests.

    Example:
        # Simple snapshot for testing
        snapshot = ContextSnapshot()

        # Full snapshot with extensions
        @dataclass(frozen=True)
        class MyExtensions(ExtensionBundle):
            custom_field: str = ""

        snapshot: ContextSnapshot[MyExtensions] = ContextSnapshot(
            run_id=RunIdentity(pipeline_run_id=uuid4()),
            extensions=MyExtensions(custom_field="value"),
        )
    """

    # === Composed Data Bundles ===
    run_id: RunIdentity = field(default_factory=RunIdentity)
    enrichments: Enrichments | None = None
    conversation: Conversation | None = None

    # === User-Defined Extensions (Generic[T]) ===
    extensions: T | None = None

    # === Input Context ===
    input_text: str | None = None  # Raw user input (text or STT transcript)
    input_audio_duration_ms: int | None = None

    # === Topology / Configuration ===
    topology: str | None = None  # e.g., "fast_kernel", "accurate_kernel"
    execution_mode: str | None = None  # e.g., "practice", "roleplay", "doc_edit"

    # === Metadata ===
    created_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    # === Backwards Compatibility Properties ===
    # These provide access to fields in the old flat structure

    @property
    def pipeline_run_id(self) -> UUID | None:
        """Pipeline run identifier (backwards compat)."""
        return self.run_id.pipeline_run_id

    @property
    def request_id(self) -> UUID | None:
        """Request identifier (backwards compat)."""
        return self.run_id.request_id

    @property
    def session_id(self) -> UUID | None:
        """Session identifier (backwards compat)."""
        return self.run_id.session_id

    @property
    def user_id(self) -> UUID | None:
        """User identifier (backwards compat)."""
        return self.run_id.user_id

    @property
    def org_id(self) -> UUID | None:
        """Organization identifier (backwards compat)."""
        return self.run_id.org_id

    @property
    def interaction_id(self) -> UUID | None:
        """Interaction identifier (backwards compat)."""
        return self.run_id.interaction_id

    @property
    def messages(self) -> list[Message]:
        """Message history (backwards compat)."""
        if self.conversation is None:
            return []
        return self.conversation.messages

    @property
    def routing_decision(self) -> RoutingDecision | None:
        """Routing decision (backwards compat)."""
        if self.conversation is None:
            return None
        return self.conversation.routing_decision

    @property
    def profile(self) -> ProfileEnrichment | None:
        """Profile enrichment (backwards compat)."""
        if self.enrichments is None:
            return None
        return self.enrichments.profile

    @property
    def memory(self) -> MemoryEnrichment | None:
        """Memory enrichment (backwards compat)."""
        if self.enrichments is None:
            return None
        return self.enrichments.memory

    @property
    def documents(self) -> list[DocumentEnrichment]:
        """Document enrichments (backwards compat)."""
        if self.enrichments is None:
            return []
        return self.enrichments.documents

    @property
    def web_results(self) -> list[dict[str, Any]]:
        """Web results (backwards compat)."""
        if self.enrichments is None:
            return []
        return self.enrichments.web_results

    # === Serialization ===

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict.

        Returns:
            Dictionary representation with all nested objects serialized.
        """
        result: dict[str, Any] = {
            # Composed bundles
            "run_id": self.run_id.to_dict(),
            "enrichments": self.enrichments.to_dict() if self.enrichments else None,
            "conversation": self.conversation.to_dict() if self.conversation else None,
            # Extensions
            "extensions": None,
            "extensions_type": None,
            # Input context
            "input_text": self.input_text,
            "input_audio_duration_ms": self.input_audio_duration_ms,
            # Topology
            "topology": self.topology,
            "execution_mode": self.execution_mode,
            # Metadata
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

        # Serialize extensions if present
        if self.extensions is not None:
            result["extensions"] = self.extensions.to_dict()
            result["extensions_type"] = type(self.extensions).__name__

        # Add flat fields for backwards compatibility
        result.update({
            "pipeline_run_id": str(self.run_id.pipeline_run_id) if self.run_id.pipeline_run_id else None,
            "request_id": str(self.run_id.request_id) if self.run_id.request_id else None,
            "session_id": str(self.run_id.session_id) if self.run_id.session_id else None,
            "user_id": str(self.run_id.user_id) if self.run_id.user_id else None,
            "org_id": str(self.run_id.org_id) if self.run_id.org_id else None,
            "interaction_id": str(self.run_id.interaction_id) if self.run_id.interaction_id else None,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                    "metadata": m.metadata,
                }
                for m in self.messages
            ],
            "routing_decision": (
                {
                    "agent_id": self.routing_decision.agent_id,
                    "pipeline_name": self.routing_decision.pipeline_name,
                    "topology": self.routing_decision.topology,
                    "reason": self.routing_decision.reason,
                }
                if self.routing_decision
                else None
            ),
            "profile": self.profile.to_dict() if self.profile else None,
            "memory": self.memory.to_dict() if self.memory else None,
            "documents": [d.to_dict() for d in self.documents],
            "web_results": self.web_results,
        })

        return result

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        extension_types: dict[str, type[T]] | None = None,
    ) -> ContextSnapshot[T]:
        """Create ContextSnapshot from dictionary.

        Handles both new composed structure and legacy flat structure
        for backwards compatibility.

        Args:
            data: Dictionary with snapshot data.
            extension_types: Optional registry mapping extension type names
                to their classes for deserialization.

        Returns:
            ContextSnapshot instance.
        """
        # Parse run_id - prefer new composed format, fall back to flat
        if data.get("run_id") and isinstance(data["run_id"], dict):
            run_id = RunIdentity.from_dict(data["run_id"])
        else:
            # Legacy flat format
            run_id = RunIdentity(
                pipeline_run_id=UUID(data["pipeline_run_id"]) if data.get("pipeline_run_id") else None,
                request_id=UUID(data["request_id"]) if data.get("request_id") else None,
                session_id=UUID(data["session_id"]) if data.get("session_id") else None,
                user_id=UUID(data["user_id"]) if data.get("user_id") else None,
                org_id=UUID(data["org_id"]) if data.get("org_id") else None,
                interaction_id=UUID(data["interaction_id"]) if data.get("interaction_id") else None,
            )

        # Parse enrichments - prefer new composed format, allow new canonical bundles, fall back to flat legacy fields
        enrichments = None
        if data.get("enrichments") and isinstance(data["enrichments"], dict):
            enrichments = Enrichments.from_dict(data["enrichments"])
        else:
            # Legacy flat format - build Enrichments from flat fields
            profile = None
            if data.get("profile"):
                profile = ProfileEnrichment.from_dict(data["profile"])

            memory = None
            if data.get("memory"):
                memory = MemoryEnrichment.from_dict(data["memory"])

            documents = [
                DocumentEnrichment.from_dict(d) for d in data.get("documents", [])
            ]

            web_results = data.get("web_results", [])

            if profile or memory or documents or web_results:
                enrichments = Enrichments(
                    profile=profile,
                    memory=memory,
                    documents=documents,
                    web_results=web_results,
                )

        # Parse conversation - prefer new composed format, allow new canonical structures, fall back to flat
        conversation = None
        if data.get("conversation") and isinstance(data["conversation"], dict):
            conversation = Conversation.from_dict(data["conversation"])
        else:
            # Legacy flat format - build Conversation from flat fields
            messages = []
            for m in data.get("messages", []):
                timestamp = None
                if m.get("timestamp"):
                    timestamp = datetime.fromisoformat(m["timestamp"])
                messages.append(
                    Message(
                        role=m["role"],
                        content=m["content"],
                        timestamp=timestamp,
                        metadata=m.get("metadata", {}),
                    )
                )

            routing_decision = None
            routing = data.get("routing_decision")
            if routing and isinstance(routing, dict):
                routing_decision = RoutingDecision(
                    agent_id=routing.get("agent_id"),
                    pipeline_name=routing.get("pipeline_name"),
                    topology=routing.get("topology"),
                    reason=routing.get("reason"),
                )

            if messages or routing_decision:
                conversation = Conversation(
                    messages=messages,
                    routing_decision=routing_decision,
                )

        # Parse extensions
        extensions = None
        if data.get("extensions") and data.get("extensions_type"):
            ext_type_name = data["extensions_type"]
            if extension_types and ext_type_name in extension_types:
                ext_cls = extension_types[ext_type_name]
                extensions = ext_cls.from_dict(data["extensions"])

        # Parse created_at
        created_at = _utc_now()
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        return cls(
            run_id=run_id,
            enrichments=enrichments,
            conversation=conversation,
            extensions=extensions,
            input_text=data.get("input_text"),
            input_audio_duration_ms=data.get("input_audio_duration_ms"),
            topology=data.get("topology"),
            execution_mode=data.get("execution_mode"),
            created_at=created_at,
            metadata=data.get("metadata", {}),
        )

    # === Utility Methods ===

    def with_run_id(self, run_id: RunIdentity) -> ContextSnapshot[T]:
        """Return a copy with a new run_id.

        Args:
            run_id: The new RunIdentity.

        Returns:
            New ContextSnapshot with updated run_id.
        """
        return ContextSnapshot(
            run_id=run_id,
            enrichments=self.enrichments,
            conversation=self.conversation,
            extensions=self.extensions,
            input_text=self.input_text,
            input_audio_duration_ms=self.input_audio_duration_ms,
            topology=self.topology,
            execution_mode=self.execution_mode,
            created_at=self.created_at,
            metadata=self.metadata,
        )

    def with_enrichments(self, enrichments: Enrichments) -> ContextSnapshot[T]:
        """Return a copy with new enrichments.

        Args:
            enrichments: The new Enrichments bundle.

        Returns:
            New ContextSnapshot with updated enrichments.
        """
        return ContextSnapshot(
            run_id=self.run_id,
            enrichments=enrichments,
            conversation=self.conversation,
            extensions=self.extensions,
            input_text=self.input_text,
            input_audio_duration_ms=self.input_audio_duration_ms,
            topology=self.topology,
            execution_mode=self.execution_mode,
            created_at=self.created_at,
            metadata=self.metadata,
        )

    def with_conversation(self, conversation: Conversation) -> ContextSnapshot[T]:
        """Return a copy with new conversation.

        Args:
            conversation: The new Conversation bundle.

        Returns:
            New ContextSnapshot with updated conversation.
        """
        return ContextSnapshot(
            run_id=self.run_id,
            enrichments=self.enrichments,
            conversation=conversation,
            extensions=self.extensions,
            input_text=self.input_text,
            input_audio_duration_ms=self.input_audio_duration_ms,
            topology=self.topology,
            execution_mode=self.execution_mode,
            created_at=self.created_at,
            metadata=self.metadata,
        )

    def with_extensions(self, extensions: T) -> ContextSnapshot[T]:
        """Return a copy with new extensions.

        Args:
            extensions: The new extensions bundle.

        Returns:
            New ContextSnapshot with updated extensions.
        """
        return ContextSnapshot(
            run_id=self.run_id,
            enrichments=self.enrichments,
            conversation=self.conversation,
            extensions=extensions,
            input_text=self.input_text,
            input_audio_duration_ms=self.input_audio_duration_ms,
            topology=self.topology,
            execution_mode=self.execution_mode,
            created_at=self.created_at,
            metadata=self.metadata,
        )


__all__ = [
    "ContextSnapshot",
    "T",
]
