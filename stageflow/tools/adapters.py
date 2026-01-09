"""Context adapters for backwards compatibility.

This module provides adapters that allow dict-based contexts to be used
with the ExecutionContext protocol, enabling backwards compatibility
with legacy code that passes dict contexts to tools.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

logger = logging.getLogger("stageflow.tools.adapters")


@dataclass
class DictContextAdapter:
    """Adapts a dict to the ExecutionContext protocol.
    
    This adapter allows legacy code that uses dict contexts to work
    with the new ExecutionContext-based tool system.
    
    Example:
        ctx_dict = {"pipeline_run_id": "...", "execution_mode": "practice"}
        adapted = DictContextAdapter(ctx_dict)
        await executor.execute(action, adapted)
    """
    
    _data: dict[str, Any]
    
    @property
    def pipeline_run_id(self) -> UUID | None:
        """Pipeline run identifier for correlation."""
        val = self._data.get("pipeline_run_id")
        if val is None:
            return None
        if isinstance(val, UUID):
            return val
        try:
            return UUID(str(val))
        except (ValueError, TypeError):
            return None
    
    @property
    def request_id(self) -> UUID | None:
        """Request identifier for tracing."""
        val = self._data.get("request_id")
        if val is None:
            return None
        if isinstance(val, UUID):
            return val
        try:
            return UUID(str(val))
        except (ValueError, TypeError):
            return None
    
    @property
    def execution_mode(self) -> str | None:
        """Current execution mode."""
        return self._data.get("execution_mode")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for serialization."""
        return self._data.copy()
    
    def try_emit_event(self, type: str, data: dict[str, Any]) -> None:
        """Emit an event without blocking (fire-and-forget).
        
        For dict contexts, events are logged at debug level since
        there's no event sink available.
        """
        enriched_data = {
            "pipeline_run_id": str(self.pipeline_run_id) if self.pipeline_run_id else None,
            "request_id": str(self.request_id) if self.request_id else None,
            "execution_mode": self.execution_mode,
            **data,
        }
        logger.debug(f"Event (dict context): {type}", extra=enriched_data)


def adapt_context(ctx: Any) -> Any:
    """Adapt a context to ExecutionContext if needed.
    
    If the context is already an ExecutionContext (has required methods),
    returns it unchanged. If it's a dict, wraps it in DictContextAdapter.
    
    Args:
        ctx: Context to adapt (ExecutionContext, dict, or other)
        
    Returns:
        ExecutionContext-compatible object
        
    Raises:
        TypeError: If context type is not supported
    """
    # Check if it already implements ExecutionContext
    if hasattr(ctx, 'pipeline_run_id') and hasattr(ctx, 'to_dict') and hasattr(ctx, 'try_emit_event'):
        return ctx
    
    # Adapt dict to ExecutionContext
    if isinstance(ctx, dict):
        return DictContextAdapter(ctx)
    
    raise TypeError(f"Unsupported context type: {type(ctx).__name__}")


__all__ = [
    "DictContextAdapter",
    "adapt_context",
]
