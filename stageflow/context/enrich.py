"""Context enrichment utilities for ENRICH stages.

Provides context utilization tracking, truncation event emission,
version metadata management, and conflict detection for context updates.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("stageflow.context.enrich")


@dataclass
class ContextUtilization:
    """Track context window utilization.

    Monitors token usage and provides metrics for context management.
    """

    max_tokens: int
    used_tokens: int = 0
    reserved_tokens: int = 0  # For response generation

    @property
    def available_tokens(self) -> int:
        """Tokens available for new content."""
        return max(0, self.max_tokens - self.used_tokens - self.reserved_tokens)

    @property
    def utilization(self) -> float:
        """Current utilization as percentage (0-1)."""
        return self.used_tokens / self.max_tokens if self.max_tokens > 0 else 0.0

    @property
    def is_near_limit(self) -> bool:
        """Check if context is near capacity (>80%)."""
        return self.utilization > 0.8

    @property
    def is_at_limit(self) -> bool:
        """Check if context is at or over capacity."""
        return self.used_tokens >= self.max_tokens - self.reserved_tokens

    def can_fit(self, token_count: int) -> bool:
        """Check if additional tokens can fit."""
        return token_count <= self.available_tokens

    def add(self, token_count: int) -> bool:
        """Add tokens to usage tracking.

        Returns:
            True if tokens were added, False if would exceed limit
        """
        if not self.can_fit(token_count):
            return False
        self.used_tokens += token_count
        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "max_tokens": self.max_tokens,
            "used_tokens": self.used_tokens,
            "reserved_tokens": self.reserved_tokens,
            "available_tokens": self.available_tokens,
            "utilization": self.utilization,
            "is_near_limit": self.is_near_limit,
        }


@dataclass
class TruncationEvent:
    """Record of a context truncation event."""

    timestamp: datetime
    original_tokens: int
    truncated_tokens: int
    strategy: str  # "head", "tail", "middle", "semantic"
    content_type: str  # "document", "conversation", "retrieval"
    reason: str
    preserved_ratio: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def tokens_removed(self) -> int:
        """Number of tokens removed."""
        return self.original_tokens - self.truncated_tokens

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for event emission."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "original_tokens": self.original_tokens,
            "truncated_tokens": self.truncated_tokens,
            "tokens_removed": self.tokens_removed,
            "strategy": self.strategy,
            "content_type": self.content_type,
            "reason": self.reason,
            "preserved_ratio": self.preserved_ratio,
            "metadata": self.metadata,
        }


class TruncationTracker:
    """Track truncation events for observability."""

    def __init__(self, event_sink: Any = None) -> None:
        self._events: list[TruncationEvent] = []
        self._event_sink = event_sink

    def record_truncation(
        self,
        original_tokens: int,
        truncated_tokens: int,
        strategy: str,
        content_type: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> TruncationEvent:
        """Record a truncation event.

        Args:
            original_tokens: Token count before truncation
            truncated_tokens: Token count after truncation
            strategy: Truncation strategy used
            content_type: Type of content truncated
            reason: Why truncation was needed
            metadata: Additional context

        Returns:
            The recorded TruncationEvent
        """
        preserved_ratio = truncated_tokens / original_tokens if original_tokens > 0 else 1.0

        event = TruncationEvent(
            timestamp=datetime.now(UTC),
            original_tokens=original_tokens,
            truncated_tokens=truncated_tokens,
            strategy=strategy,
            content_type=content_type,
            reason=reason,
            preserved_ratio=preserved_ratio,
            metadata=metadata or {},
        )

        self._events.append(event)

        # Emit event
        if self._event_sink:
            try:
                self._event_sink.try_emit(
                    "context.truncation",
                    event.to_dict(),
                )
            except Exception as e:
                logger.warning(f"Failed to emit truncation event: {e}")

        logger.info(
            f"Context truncated: {original_tokens} -> {truncated_tokens} tokens "
            f"({strategy}, {preserved_ratio:.1%} preserved)",
            extra={
                "event": "context_truncation",
                **event.to_dict(),
            },
        )

        return event

    @property
    def total_tokens_removed(self) -> int:
        """Total tokens removed across all truncations."""
        return sum(e.tokens_removed for e in self._events)

    @property
    def event_count(self) -> int:
        """Number of truncation events recorded."""
        return len(self._events)

    def get_summary(self) -> dict[str, Any]:
        """Get summary of truncation events."""
        if not self._events:
            return {
                "event_count": 0,
                "total_tokens_removed": 0,
                "strategies_used": [],
            }

        return {
            "event_count": len(self._events),
            "total_tokens_removed": self.total_tokens_removed,
            "strategies_used": list({e.strategy for e in self._events}),
            "content_types": list({e.content_type for e in self._events}),
            "avg_preserved_ratio": sum(e.preserved_ratio for e in self._events) / len(self._events),
        }


@dataclass
class VersionMetadata:
    """Version metadata for context content.

    Tracks document versions, retrieval timestamps, and staleness.
    """

    content_id: str
    version: str
    retrieved_at: datetime
    source: str
    checksum: str | None = None
    ttl_seconds: int | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def age_seconds(self) -> float:
        """Age of content since retrieval."""
        return (datetime.now(UTC) - self.retrieved_at).total_seconds()

    @property
    def is_stale(self) -> bool:
        """Check if content exceeds TTL."""
        if self.ttl_seconds is None:
            return False
        return self.age_seconds > self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content_id": self.content_id,
            "version": self.version,
            "retrieved_at": self.retrieved_at.isoformat(),
            "source": self.source,
            "checksum": self.checksum,
            "ttl_seconds": self.ttl_seconds,
            "age_seconds": self.age_seconds,
            "is_stale": self.is_stale,
            "tags": self.tags,
        }

    @classmethod
    def create(
        cls,
        content_id: str,
        version: str,
        source: str,
        content: str | bytes | None = None,
        ttl_seconds: int | None = None,
        tags: list[str] | None = None,
    ) -> VersionMetadata:
        """Create version metadata with optional checksum.

        Args:
            content_id: Unique content identifier
            version: Version string
            source: Content source (e.g., "vector_db", "api")
            content: Optional content for checksum calculation
            ttl_seconds: Time-to-live for staleness detection
            tags: Optional tags for categorization
        """
        checksum = None
        if content is not None:
            if isinstance(content, str):
                content = content.encode()
            checksum = hashlib.sha256(content).hexdigest()[:16]

        return cls(
            content_id=content_id,
            version=version,
            retrieved_at=datetime.now(UTC),
            source=source,
            checksum=checksum,
            ttl_seconds=ttl_seconds,
            tags=tags or [],
        )


@dataclass
class ConflictResolution:
    """Result of a conflict detection check."""

    has_conflict: bool
    field: str | None = None
    old_value: Any = None
    new_value: Any = None
    resolution: str | None = None  # "keep_old", "keep_new", "merge", "error"
    merged_value: Any = None


class ConflictDetector:
    """Detect and resolve conflicts in context updates.

    Supports multiple resolution strategies for concurrent updates.
    """

    def __init__(
        self,
        default_strategy: str = "keep_new",
        merge_strategies: dict[str, str] | None = None,
    ) -> None:
        """Initialize conflict detector.

        Args:
            default_strategy: Default resolution strategy
            merge_strategies: Per-field strategy overrides
        """
        self.default_strategy = default_strategy
        self.merge_strategies = merge_strategies or {}

    def check_and_resolve(
        self,
        field: str,
        old_value: Any,
        new_value: Any,
    ) -> ConflictResolution:
        """Check for conflict and resolve if needed.

        Args:
            field: Field name being updated
            old_value: Current value
            new_value: New value

        Returns:
            ConflictResolution with resolution details
        """
        # No conflict if old value is None
        if old_value is None:
            return ConflictResolution(
                has_conflict=False,
                field=field,
                new_value=new_value,
            )

        # No conflict if values are equal
        if old_value == new_value:
            return ConflictResolution(
                has_conflict=False,
                field=field,
                old_value=old_value,
                new_value=new_value,
            )

        # Conflict detected - resolve based on strategy
        strategy = self.merge_strategies.get(field, self.default_strategy)

        if strategy == "keep_old":
            return ConflictResolution(
                has_conflict=True,
                field=field,
                old_value=old_value,
                new_value=new_value,
                resolution="keep_old",
                merged_value=old_value,
            )

        if strategy == "keep_new":
            return ConflictResolution(
                has_conflict=True,
                field=field,
                old_value=old_value,
                new_value=new_value,
                resolution="keep_new",
                merged_value=new_value,
            )

        if strategy == "merge":
            merged = self._merge_values(old_value, new_value)
            return ConflictResolution(
                has_conflict=True,
                field=field,
                old_value=old_value,
                new_value=new_value,
                resolution="merge",
                merged_value=merged,
            )

        if strategy == "error":
            return ConflictResolution(
                has_conflict=True,
                field=field,
                old_value=old_value,
                new_value=new_value,
                resolution="error",
            )

        # Default to keep_new
        return ConflictResolution(
            has_conflict=True,
            field=field,
            old_value=old_value,
            new_value=new_value,
            resolution="keep_new",
            merged_value=new_value,
        )

    def _merge_values(self, old: Any, new: Any) -> Any:
        """Merge two values if possible.

        Supports:
        - Lists: concatenate
        - Dicts: merge recursively
        - Strings: concatenate with separator
        - Numbers: keep new
        """
        if isinstance(old, list) and isinstance(new, list):
            # Deduplicate if items are hashable
            try:
                seen = set(old)
                return old + [x for x in new if x not in seen]
            except TypeError:
                return old + new

        if isinstance(old, dict) and isinstance(new, dict):
            merged = dict(old)
            for key, value in new.items():
                if key in merged:
                    # Recursive merge
                    merged[key] = self._merge_values(merged[key], value)
                else:
                    merged[key] = value
            return merged

        if isinstance(old, str) and isinstance(new, str):
            return f"{old}\n{new}"

        # Default to new value
        return new


__all__ = [
    "ConflictDetector",
    "ConflictResolution",
    "ContextUtilization",
    "TruncationEvent",
    "TruncationTracker",
    "VersionMetadata",
]
