"""Stageflow context module - execution context types.

This module provides the context types used throughout stageflow:

- **ContextSnapshot**: Immutable view of execution context (Generic[T] for extensions)
- **RunIdentity**: Grouped run identification fields
- **Enrichments**: Grouped enrichment data (profile, memory, documents, web)
- **Conversation**: Grouped conversation data (messages, routing)
- **ExtensionBundle**: Base class for user-defined typed extensions
- **OutputBag**: Append-only output collection with version tracking
"""

from stageflow.context.bag import ContextBag, DataConflictError
from stageflow.context.context_snapshot import ContextSnapshot
from stageflow.context.conversation import Conversation
from stageflow.context.enrichments import (
    DocumentEnrichment,
    Enrichments,
    MemoryEnrichment,
    ProfileEnrichment,
)
from stageflow.context.extensions import ExtensionBundle
from stageflow.context.identity import RunIdentity
from stageflow.context.output_bag import OutputBag, OutputConflictError, OutputEntry
from stageflow.context.types import Message, RoutingDecision

__all__ = [
    # Core snapshot
    "ContextSnapshot",
    # Composition types
    "RunIdentity",
    "Enrichments",
    "Conversation",
    # Enrichment types
    "DocumentEnrichment",
    "MemoryEnrichment",
    "ProfileEnrichment",
    # Message types
    "Message",
    "RoutingDecision",
    # Extensions
    "ExtensionBundle",
    # Output bag (new)
    "OutputBag",
    "OutputEntry",
    "OutputConflictError",
    # Legacy (deprecated)
    "ContextBag",
    "DataConflictError",
]
