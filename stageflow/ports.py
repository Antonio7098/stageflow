"""Protocol definitions for stageflow extension points.

This module defines all the protocols (interfaces) that allow stageflow to be
extended without modifying core code. Following the Dependency Inversion Principle,
high-level modules depend on these abstractions, not on concrete implementations.

Protocols:
    EventSink: Event persistence/emission
    RunStore: Pipeline run persistence
    ConfigProvider: Configuration access
    
Dataclasses:
    CorrelationIds: Generic correlation IDs for tracing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class EventSink(Protocol):
    """Protocol for event persistence/emission.
    
    Implementations handle where events go - database, message queue,
    logging system, or just discarded (NoOp).
    
    Example:
        class DatabaseEventSink:
            async def emit(self, *, type: str, data: dict | None) -> None:
                await db.insert("events", {"type": type, "data": data})
                
            def try_emit(self, *, type: str, data: dict | None) -> None:
                asyncio.create_task(self.emit(type=type, data=data))
    """
    
    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        """Emit an event asynchronously.
        
        Args:
            type: Event type string (e.g., "stage.stt.completed")
            data: Event payload data
        """
        ...
    
    def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        """Emit an event without blocking (fire-and-forget).
        
        This method should not raise exceptions. Failed emissions
        should be logged internally.
        
        Args:
            type: Event type string
            data: Event payload data
        """
        ...


@runtime_checkable
class RunStore(Protocol):
    """Protocol for pipeline run persistence.
    
    Implementations handle how pipeline runs are stored and retrieved.
    This could be a database, in-memory store, or external service.
    
    Example:
        class PostgresRunStore:
            async def create_run(self, run_id: UUID, **metadata) -> PipelineRun:
                return await db.insert("pipeline_runs", {"id": run_id, **metadata})
    """
    
    async def create_run(
        self,
        run_id: UUID,
        *,
        service: str,
        topology: str | None = None,
        behavior: str | None = None,
        status: str = "created",
        **metadata: Any,
    ) -> Any:
        """Create a new pipeline run record.
        
        Args:
            run_id: Unique identifier for the run
            service: Service name (e.g., "voice", "chat")
            topology: Pipeline topology name
            behavior: Behavior mode
            status: Initial status
            **metadata: Additional metadata
            
        Returns:
            The created run object
        """
        ...
    
    async def update_status(
        self,
        run_id: UUID,
        status: str,
        *,
        error: str | None = None,
        duration_ms: int | None = None,
        **data: Any,
    ) -> None:
        """Update a pipeline run's status.
        
        Args:
            run_id: Run identifier
            status: New status
            error: Error message if failed
            duration_ms: Total duration in milliseconds
            **data: Additional data to store
        """
        ...
    
    async def get_run(self, run_id: UUID) -> Any | None:
        """Retrieve a pipeline run by ID.
        
        Args:
            run_id: Run identifier
            
        Returns:
            The run object or None if not found
        """
        ...


@runtime_checkable
class ConfigProvider(Protocol):
    """Protocol for configuration access.
    
    Implementations provide configuration values from environment,
    files, databases, or other sources.
    
    Example:
        class EnvConfigProvider:
            def get(self, key: str, default: Any = None) -> Any:
                return os.environ.get(key, default)
    """
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        ...


@dataclass(frozen=True, slots=True)
class CorrelationIds:
    """Generic correlation IDs for distributed tracing.
    
    These IDs are propagated through the pipeline to correlate
    logs, traces, and events across services.
    
    Attributes:
        run_id: Pipeline run identifier
        request_id: HTTP/WS request identifier
        trace_id: Distributed tracing ID (e.g., OpenTelemetry)
        session_id: User session identifier
        user_id: User identifier
        org_id: Organization/tenant identifier
        extra: Extension point for app-specific IDs
        
    Example:
        ids = CorrelationIds(
            run_id=uuid4(),
            request_id=uuid4(),
            trace_id="abc123",
            extra={"interaction_id": str(interaction_id)}
        )
    """
    
    run_id: UUID | None = None
    request_id: UUID | None = None
    trace_id: str | None = None
    session_id: UUID | None = None
    user_id: UUID | None = None
    org_id: UUID | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        result: dict[str, Any] = {}
        if self.run_id:
            result["pipeline_run_id"] = str(self.run_id)
        if self.request_id:
            result["request_id"] = str(self.request_id)
        if self.trace_id:
            result["trace_id"] = self.trace_id
        if self.session_id:
            result["session_id"] = str(self.session_id)
        if self.user_id:
            result["user_id"] = str(self.user_id)
        if self.org_id:
            result["org_id"] = str(self.org_id)
        result.update(self.extra)
        return result


__all__ = [
    "EventSink",
    "RunStore", 
    "ConfigProvider",
    "CorrelationIds",
]
