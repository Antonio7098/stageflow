"""ContextSnapshot - immutable view passed to Agents.

ContextSnapshot is an immutable, serializable view of the world that Agents receive
when planning work. It contains:

- run identity (user, session, org, request)
- normalized message history
- profile and canonical memory view
- enrichments (profile, memory, docs, etc.)
- routing decision
- execution_mode flag
- extensions for application-specific data

ContextSnapshot is serializable to JSON to support unit testing and Central Pulse replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from .enrichments import DocumentEnrichment, MemoryEnrichment, ProfileEnrichment
from .types import Message, RoutingDecision


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    """Immutable view passed to Agents containing run identity, messages, enrichments, and routing decision.

    This is the canonical input to Agent.plan(). It is:
    - Immutable (frozen dataclass)
    - Serializable to JSON (for testing and Central Pulse replay)
    - Complete (contains everything the Agent needs to plan)
    """

    # === Run Identity ===
    pipeline_run_id: UUID | None
    request_id: UUID | None
    session_id: UUID | None
    user_id: UUID | None
    org_id: UUID | None
    interaction_id: UUID | None

    # === Topology / Configuration / Execution Mode ===
    topology: str | None  # e.g., "fast_kernel", "accurate_kernel"
    execution_mode: str | None  # e.g., "practice", "roleplay", "doc_edit"

    # === Message History ===
    messages: list[Message] = field(default_factory=list)

    # === Routing Decision ===
    routing_decision: RoutingDecision | None = None

    # === Enrichments ===
    profile: ProfileEnrichment | None = None
    memory: MemoryEnrichment | None = None
    documents: list[DocumentEnrichment] = field(default_factory=list)
    web_results: list[dict[str, Any]] = field(default_factory=list)

    # === Input Context ===
    input_text: str | None = None  # Raw user input (text or STT transcript)
    input_audio_duration_ms: int | None = None

    # === Extensions ===
    # Application-specific extensions stored as key-value pairs
    extensions: dict[str, Any] = field(default_factory=dict)

    # === Metadata ===
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "request_id": str(self.request_id) if self.request_id else None,
            "session_id": str(self.session_id) if self.session_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "org_id": str(self.org_id) if self.org_id else None,
            "interaction_id": str(self.interaction_id) if self.interaction_id else None,
            "topology": self.topology,
            "execution_mode": self.execution_mode,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                    "metadata": m.metadata,
                }
                for m in self.messages
            ],
            "routing_decision": {
                "agent_id": self.routing_decision.agent_id,
                "pipeline_name": self.routing_decision.pipeline_name,
                "topology": self.routing_decision.topology,
                "reason": self.routing_decision.reason,
            }
            if self.routing_decision
            else None,
            "profile": {
                "user_id": str(self.profile.user_id) if self.profile else None,
                "display_name": self.profile.display_name if self.profile else None,
                "preferences": self.profile.preferences if self.profile else {},
                "goals": self.profile.goals if self.profile else [],
            }
            if self.profile
            else None,
            "memory": {
                "recent_topics": self.memory.recent_topics if self.memory else [],
                "key_facts": self.memory.key_facts if self.memory else [],
                "interaction_history_summary": self.memory.interaction_history_summary
                if self.memory
                else None,
            }
            if self.memory
            else None,
            "documents": [
                {
                    "document_id": d.document_id,
                    "document_type": d.document_type,
                    "blocks": d.blocks,
                    "metadata": d.metadata,
                }
                for d in self.documents
            ],
            "web_results": self.web_results,
            "input_text": self.input_text,
            "input_audio_duration_ms": self.input_audio_duration_ms,
            "extensions": self.extensions,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextSnapshot:
        """Create from JSON dict."""
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
        if data.get("routing_decision"):
            rd = data["routing_decision"]
            routing_decision = RoutingDecision(
                agent_id=rd["agent_id"],
                pipeline_name=rd["pipeline_name"],
                topology=rd["topology"],
                reason=rd.get("reason"),
            )

        profile = None
        if data.get("profile"):
            p = data["profile"]
            profile = ProfileEnrichment(
                user_id=UUID(p["user_id"])
                if p.get("user_id")
                else UUID("00000000-0000-0000-0000-000000000000"),
                display_name=p.get("display_name"),
                preferences=p.get("preferences", {}),
                goals=p.get("goals", []),
            )

        memory = None
        if data.get("memory"):
            m = data["memory"]
            memory = MemoryEnrichment(
                recent_topics=m.get("recent_topics", []),
                key_facts=m.get("key_facts", []),
                interaction_history_summary=m.get("interaction_history_summary"),
            )

        documents = []
        for d in data.get("documents", []):
            documents.append(
                DocumentEnrichment(
                    document_id=d.get("document_id"),
                    document_type=d.get("document_type"),
                    blocks=d.get("blocks", []),
                    metadata=d.get("metadata", {}),
                )
            )

        created_at = datetime.utcnow()
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        return cls(
            pipeline_run_id=UUID(data["pipeline_run_id"]) if data.get("pipeline_run_id") else None,
            request_id=UUID(data["request_id"]) if data.get("request_id") else None,
            session_id=UUID(data["session_id"]) if data.get("session_id") else None,
            user_id=UUID(data["user_id"]) if data.get("user_id") else None,
            org_id=UUID(data["org_id"]) if data.get("org_id") else None,
            interaction_id=UUID(data["interaction_id"]) if data.get("interaction_id") else None,
            topology=data.get("topology"),
            execution_mode=data.get("execution_mode"),
            messages=messages,
            routing_decision=routing_decision,
            profile=profile,
            memory=memory,
            documents=documents,
            web_results=data.get("web_results", []),
            input_text=data.get("input_text"),
            input_audio_duration_ms=data.get("input_audio_duration_ms"),
            extensions=data.get("extensions", {}),
            created_at=created_at,
            metadata=data.get("metadata", {}),
        )
