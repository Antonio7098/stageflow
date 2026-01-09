"""Agent package containing ContextSnapshot and related types."""

from stageflow.context import (
    ContextSnapshot,
    DocumentEnrichment,
    MemoryEnrichment,
    Message,
    ProfileEnrichment,
    RoutingDecision,
)

__all__ = [
    "ContextSnapshot",
    "Message",
    "RoutingDecision",
    "ProfileEnrichment",
    "MemoryEnrichment",
    "DocumentEnrichment",
]
