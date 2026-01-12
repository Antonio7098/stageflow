"""Conversation - Grouped conversation/chat data.

This module provides the Conversation dataclass that groups message history
and routing decisions into a single optional bundle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from stageflow.context.types import Message, RoutingDecision


@dataclass(frozen=True, slots=True)
class Conversation:
    """Grouped conversation data bundle.

    Combines message history and routing decisions into a single
    optional bundle. When a ContextSnapshot has conversation=None,
    it means this is not a conversational context.

    Attributes:
        messages: Ordered list of conversation messages.
        routing_decision: The routing decision made by the router.

    Example:
        conversation = Conversation(
            messages=[
                Message(role="user", content="Hello"),
                Message(role="assistant", content="Hi there!"),
            ],
            routing_decision=RoutingDecision(
                agent_id="coach",
                pipeline_name="practice",
                topology="fast_kernel",
            ),
        )
    """

    messages: list[Message] = field(default_factory=list)
    routing_decision: RoutingDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
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
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Conversation:
        """Create from dictionary."""
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

        return cls(
            messages=messages,
            routing_decision=routing_decision,
        )

    @property
    def last_user_message(self) -> Message | None:
        """Get the last user message in the conversation."""
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg
        return None

    @property
    def last_assistant_message(self) -> Message | None:
        """Get the last assistant message in the conversation."""
        for msg in reversed(self.messages):
            if msg.role == "assistant":
                return msg
        return None

    @property
    def message_count(self) -> int:
        """Get the number of messages in the conversation."""
        return len(self.messages)

    def with_message(self, message: Message) -> Conversation:
        """Return a new Conversation with an additional message.

        Args:
            message: The message to add.

        Returns:
            New Conversation with the message appended.
        """
        return Conversation(
            messages=[*self.messages, message],
            routing_decision=self.routing_decision,
        )


__all__ = ["Conversation"]
