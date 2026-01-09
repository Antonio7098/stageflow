"""Tools module - capability units for agent action execution.

This module provides:
- Tool definitions with behavior gating, undo, and approval
- ToolExecutor for executing actions with full observability
- Tool registry for discovery and registration
- Undo store for reversible actions
- Approval service for HITL flows
"""

from .adapters import DictContextAdapter, adapt_context
from .approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalService,
    ApprovalStatus,
    clear_approval_service,
    get_approval_service,
    set_approval_service,
)
from .base import BaseTool, Tool
from .definitions import (
    Action,
    ToolDefinition,
    ToolHandler,
    ToolInput,
    ToolOutput,
    UndoHandler,
    UndoMetadata,
)
from .diff import (
    DiffLine,
    DiffResult,
    DiffType,
    diff_json,
    diff_structured,
    diff_text,
)
from .errors import (
    ToolApprovalDeniedError,
    ToolApprovalTimeoutError,
    ToolDeniedError,
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolUndoError,
)
from .events import (
    ApprovalDecidedEvent,
    ApprovalRequestedEvent,
    ToolCompletedEvent,
    ToolDeniedEvent,
    ToolEventBase,
    ToolFailedEvent,
    ToolInvokedEvent,
    ToolStartedEvent,
    ToolUndoFailedEvent,
    ToolUndoneEvent,
)
from .executor import ToolExecutor
from .executor_v2 import AdvancedToolExecutor, ExecutionResult, ToolExecutorConfig
from .registry import ToolRegistry, get_tool_registry, register_tool, tool
from .undo import UndoStore, clear_undo_store, get_undo_store, set_undo_store

__all__ = [
    # Base types
    "Tool",
    "BaseTool",
    # Enhanced definitions
    "Action",
    "ToolDefinition",
    "ToolInput",
    "ToolOutput",
    "ToolHandler",
    "UndoHandler",
    "UndoMetadata",
    # Diff utilities
    "DiffType",
    "DiffLine",
    "DiffResult",
    "diff_text",
    "diff_json",
    "diff_structured",
    # Errors
    "ToolError",
    "ToolNotFoundError",
    "ToolDeniedError",
    "ToolApprovalDeniedError",
    "ToolApprovalTimeoutError",
    "ToolUndoError",
    "ToolExecutionError",
    # Events
    "ToolEventBase",
    "ToolInvokedEvent",
    "ToolStartedEvent",
    "ToolCompletedEvent",
    "ToolFailedEvent",
    "ToolDeniedEvent",
    "ToolUndoneEvent",
    "ToolUndoFailedEvent",
    "ApprovalRequestedEvent",
    "ApprovalDecidedEvent",
    # Registry
    "ToolRegistry",
    "get_tool_registry",
    "register_tool",
    "tool",
    # Executors
    "ToolExecutor",
    "AdvancedToolExecutor",
    "ToolExecutorConfig",
    "ExecutionResult",
    # Undo
    "UndoStore",
    "get_undo_store",
    "set_undo_store",
    "clear_undo_store",
    # Approval
    "ApprovalStatus",
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalService",
    "get_approval_service",
    "set_approval_service",
    "clear_approval_service",
    # Adapters
    "DictContextAdapter",
    "adapt_context",
]
