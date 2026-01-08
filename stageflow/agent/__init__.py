"""ContextSnapshot - immutable view passed to Agents.

ContextSnapshot is an immutable, serializable view of the world that Agents receive
when planning work. It contains:

- run identity (user, session, org, request)
- normalized message history
- profile and canonical memory view
- active exercise state
- enrichments (profile, skills, docs, web, etc.)
- routing decision
- behavior and quality mode flags

ContextSnapshot is serializable to JSON to support unit testing and Central Pulse replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Message:
    """A single message in the conversation history."""

    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """Routing decision made by the router."""

    agent_id: str
    pipeline_name: str
    topology: str
    channel: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProfileEnrichment:
    """User profile enrichment data."""

    user_id: UUID
    display_name: str | None = None
    preferences: dict[str, Any] = field(default_factory=dict)
    goals: list[str] = field(default_factory=list)
    skill_levels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MemoryEnrichment:
    """Canonical memory view enrichment data."""

    recent_topics: list[str] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)
    interaction_history_summary: str | None = None


@dataclass(frozen=True, slots=True)
class SkillsEnrichment:
    """Skills context enrichment data."""

    active_skill_ids: list[str] = field(default_factory=list)
    current_level: str | None = None
    skill_progress: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocumentEnrichment:
    """Document context enrichment data."""

    document_id: str | None = None
    document_type: str | None = None
    blocks: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


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

    # === Topology / Configuration / Behavior ===
    topology: str | None  # e.g., "fast_kernel", "accurate_kernel"
    channel: str | None  # e.g., "text_channel", "voice_channel"
    behavior: str | None  # e.g., "practice", "roleplay", "doc_edit"

    # === Message History ===
    messages: list[Message] = field(default_factory=list)

    # === Routing Decision ===
    routing_decision: RoutingDecision | None = None

    # === Enrichments ===
    profile: ProfileEnrichment | None = None
    memory: MemoryEnrichment | None = None
    skills: SkillsEnrichment | None = None
    documents: list[DocumentEnrichment] = field(default_factory=list)
    web_results: list[dict[str, Any]] = field(default_factory=list)

    # === Active Exercise/Assessment State ===
    exercise_id: str | None = None
    assessment_state: dict[str, Any] = field(default_factory=dict)

    # === Input Context ===
    input_text: str | None = None  # Raw user input (text or STT transcript)
    input_audio_duration_ms: int | None = None

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
            "channel": self.channel,
            "behavior": self.behavior,
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
                "channel": self.routing_decision.channel,
                "reason": self.routing_decision.reason,
            }
            if self.routing_decision
            else None,
            "profile": {
                "user_id": str(self.profile.user_id) if self.profile else None,
                "display_name": self.profile.display_name if self.profile else None,
                "preferences": self.profile.preferences if self.profile else {},
                "goals": self.profile.goals if self.profile else [],
                "skill_levels": self.profile.skill_levels if self.profile else {},
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
            "skills": {
                "active_skill_ids": self.skills.active_skill_ids if self.skills else [],
                "current_level": self.skills.current_level if self.skills else None,
                "skill_progress": self.skills.skill_progress if self.skills else {},
            }
            if self.skills
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
            "exercise_id": self.exercise_id,
            "assessment_state": self.assessment_state,
            "input_text": self.input_text,
            "input_audio_duration_ms": self.input_audio_duration_ms,
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
                channel=rd["channel"],
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
                skill_levels=p.get("skill_levels", {}),
            )

        memory = None
        if data.get("memory"):
            m = data["memory"]
            memory = MemoryEnrichment(
                recent_topics=m.get("recent_topics", []),
                key_facts=m.get("key_facts", []),
                interaction_history_summary=m.get("interaction_history_summary"),
            )

        skills = None
        if data.get("skills"):
            s = data["skills"]
            skills = SkillsEnrichment(
                active_skill_ids=s.get("active_skill_ids", []),
                current_level=s.get("current_level"),
                skill_progress=s.get("skill_progress", {}),
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
            channel=data.get("channel"),
            behavior=data.get("behavior"),
            messages=messages,
            routing_decision=routing_decision,
            profile=profile,
            memory=memory,
            skills=skills,
            documents=documents,
            web_results=data.get("web_results", []),
            exercise_id=data.get("exercise_id"),
            assessment_state=data.get("assessment_state", {}),
            input_text=data.get("input_text"),
            input_audio_duration_ms=data.get("input_audio_duration_ms"),
            created_at=created_at,
            metadata=data.get("metadata", {}),
        )


__all__ = [
    "ContextSnapshot",
    "Message",
    "RoutingDecision",
    "ProfileEnrichment",
    "MemoryEnrichment",
    "SkillsEnrichment",
    "DocumentEnrichment",
]
