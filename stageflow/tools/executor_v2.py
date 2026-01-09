"""Enhanced ToolExecutor with behavior gating, telemetry, undo, and HITL approval.

This module provides the advanced ToolExecutor that supports:
- Behavior gating (restricting tools by execution mode)
- Full tool event lifecycle for observability
- Undo semantics for reversible actions
- HITL approval flow for risky actions

Follows SOLID principles:
- Single Responsibility: Each method handles one concern
- Open/Closed: Extensible via ToolDefinition, closed for modification
- Liskov Substitution: Works with any Tool/ToolDefinition implementation
- Interface Segregation: Separate protocols for different capabilities
- Dependency Inversion: Depends on abstractions (EventSink, UndoStore)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from stageflow.events import get_event_sink

from .approval import ApprovalService, get_approval_service
from .definitions import Action, ToolDefinition, ToolInput, ToolOutput, UndoMetadata
from .errors import (
    ToolApprovalDeniedError,
    ToolApprovalTimeoutError,
    ToolDeniedError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolUndoError,
)
from .events import (
    ApprovalDecidedEvent,
    ApprovalRequestedEvent,
    ToolCompletedEvent,
    ToolDeniedEvent,
    ToolFailedEvent,
    ToolInvokedEvent,
    ToolStartedEvent,
    ToolUndoFailedEvent,
    ToolUndoneEvent,
)
from .undo import UndoStore, get_undo_store

if TYPE_CHECKING:
    from stageflow.protocols import ExecutionContext

logger = logging.getLogger("stageflow.tools.executor")


@dataclass
class ToolExecutorConfig:
    """Configuration for ToolExecutor behavior."""

    approval_timeout_seconds: float = 60.0
    undo_ttl_seconds: float = 3600.0
    emit_events: bool = True
    log_level: int = logging.INFO


@dataclass
class ExecutionResult:
    """Result from executing a single tool action."""

    success: bool
    output: ToolOutput | None = None
    error: str | None = None
    duration_ms: float = 0.0
    was_approved: bool = False
    was_denied: bool = False
    denial_reason: str | None = None


class AdvancedToolExecutor:
    """Enhanced ToolExecutor with full observability and gating.

    This executor provides:
    - Behavior gating: Tools can be restricted to specific execution modes
    - Event lifecycle: Full tool.* event emission for observability
    - Undo semantics: Reversible actions with undo handlers
    - HITL approval: Human-in-the-loop approval for risky actions

    Example:
        executor = AdvancedToolExecutor()
        executor.register(ToolDefinition(
            name="edit_document",
            action_type="EDIT_DOCUMENT",
            handler=edit_handler,
            allowed_behaviors=("doc_edit", "practice"),
            requires_approval=True,
            undoable=True,
            undo_handler=undo_edit_handler,
        ))

        result = await executor.execute(action, ctx)
    """

    def __init__(
        self,
        config: ToolExecutorConfig | None = None,
        undo_store: UndoStore | None = None,
        approval_service: ApprovalService | None = None,
    ) -> None:
        self.config = config or ToolExecutorConfig()
        self._tools: dict[str, ToolDefinition] = {}
        self._undo_store = undo_store or get_undo_store()
        self._approval_service = approval_service or get_approval_service()

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition.

        Args:
            tool: The ToolDefinition to register
        """
        self._tools[tool.action_type] = tool
        logger.debug(f"Registered tool: {tool.name} for action type: {tool.action_type}")

    def get_tool(self, action_type: str) -> ToolDefinition | None:
        """Get a tool definition by action type."""
        return self._tools.get(action_type)

    def can_execute(self, action_type: str) -> bool:
        """Check if we have a tool for this action type."""
        return action_type in self._tools

    async def execute(
        self,
        action: Action,
        ctx: ExecutionContext,
    ) -> ToolOutput:
        """Execute a tool action with full lifecycle.

        This method:
        1. Looks up the tool for the action type
        2. Checks behavior gating
        3. Requests HITL approval if required
        4. Executes the tool handler
        5. Stores undo metadata if undoable
        6. Emits events throughout

        Args:
            action: The action to execute
            ctx: Execution context (PipelineContext or StageContext)

        Returns:
            ToolOutput from the tool handler

        Raises:
            ToolNotFoundError: If no tool registered for action type
            ToolDeniedError: If behavior gating blocks execution
            ToolApprovalDeniedError: If HITL approval is denied
            ToolExecutionError: If tool execution fails
        """
        tool = self._tools.get(action.type)
        if tool is None:
            raise ToolNotFoundError(action.type)

        tool_input = ToolInput.from_action(action, tool.name, ctx)

        # Emit tool.invoked
        await self._emit_tool_invoked(tool, tool_input, ctx)

        # Check behavior gating
        if not await self._check_behavior_gating(tool, tool_input, ctx):
            raise ToolDeniedError(
                tool=tool.name,
                behavior=ctx.execution_mode,
                allowed_behaviors=tool.allowed_behaviors,
            )

        # Check HITL approval if required
        if tool.requires_approval and not await self._request_and_await_approval(tool, tool_input, ctx):
            raise ToolApprovalDeniedError(tool=tool.name)

        # Execute with telemetry
        start_time = time.perf_counter()
        await self._emit_tool_started(tool, tool_input, ctx)

        try:
            output = await tool.handler(tool_input)
            duration_ms = (time.perf_counter() - start_time) * 1000

            await self._emit_tool_completed(tool, tool_input, ctx, output, duration_ms)

            # Store undo metadata if undoable and successful
            if tool.undoable and output.success and output.undo_metadata:
                await self._store_undo_metadata(tool, tool_input, output)

            return output

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_tool_failed(tool, tool_input, ctx, e, duration_ms)
            raise ToolExecutionError(
                tool=tool.name,
                action_id=action.id,
                cause=e,
            ) from e

    async def undo_action(
        self,
        action_id: UUID,
        ctx: ExecutionContext,
    ) -> bool:
        """Undo a previously executed action.

        Args:
            action_id: The action to undo
            ctx: Pipeline context

        Returns:
            True if undo succeeded, False if no undo data found

        Raises:
            ToolUndoError: If undo execution fails
        """
        metadata = await self._undo_store.get(action_id)
        if metadata is None:
            logger.warning(f"No undo metadata found for action {action_id}")
            return False

        tool = self._tools.get(metadata.tool_name)
        if tool is None or tool.undo_handler is None:
            logger.warning(f"No undo handler for tool {metadata.tool_name}")
            return False

        start_time = time.perf_counter()
        try:
            await tool.undo_handler(metadata)
            duration_ms = (time.perf_counter() - start_time) * 1000

            await self._emit_tool_undone(tool, action_id, ctx, metadata, duration_ms)
            await self._undo_store.delete(action_id)

            return True

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            await self._emit_tool_undo_failed(tool, action_id, ctx, e)
            raise ToolUndoError(
                tool=tool.name,
                action_id=action_id,
                reason=str(e),
            ) from e

    async def _check_behavior_gating(
        self,
        tool: ToolDefinition,
        tool_input: ToolInput,
        ctx: ExecutionContext,
    ) -> bool:
        """Check if behavior gating allows execution.

        Returns True if allowed, False if denied.
        """
        if tool.is_behavior_allowed(ctx.execution_mode):
            return True

        await self._emit_tool_denied(
            tool,
            tool_input,
            ctx,
            reason="behavior_not_allowed",
        )
        return False

    async def _request_and_await_approval(
        self,
        tool: ToolDefinition,
        tool_input: ToolInput,
        ctx: ExecutionContext,
    ) -> bool:
        """Request HITL approval and wait for decision.

        Returns True if approved, False if denied.
        """
        request = await self._approval_service.request_approval(
            action_id=tool_input.action_id,
            tool_name=tool.name,
            pipeline_run_id=ctx.pipeline_run_id,
            approval_message=tool.approval_message or f"Approve {tool.name}?",
            payload_summary=_summarize_payload(tool_input.payload),
        )

        await self._emit_approval_requested(tool, tool_input, ctx, request.id)

        try:
            decision = await self._approval_service.await_decision(
                request.id,
                timeout_seconds=self.config.approval_timeout_seconds,
            )
            await self._emit_approval_decided(tool, tool_input, ctx, request.id, decision.granted)
            return decision.granted

        except TimeoutError as err:
            await self._emit_tool_denied(
                tool,
                tool_input,
                ctx,
                reason="approval_timeout",
            )
            raise ToolApprovalTimeoutError(
                tool=tool.name,
                request_id=request.id,
                timeout_seconds=self.config.approval_timeout_seconds,
            ) from err

    async def _store_undo_metadata(
        self,
        tool: ToolDefinition,
        tool_input: ToolInput,
        output: ToolOutput,
    ) -> None:
        """Store undo metadata for a successful action."""
        if output.undo_metadata:
            await self._undo_store.store(
                action_id=tool_input.action_id,
                tool_name=tool.name,
                undo_data=output.undo_metadata,
                ttl_seconds=self.config.undo_ttl_seconds,
            )
            logger.debug(f"Stored undo metadata for action {tool_input.action_id}")

    # Event emission methods

    async def _emit_tool_invoked(
        self,
        tool: ToolDefinition,
        tool_input: ToolInput,
        ctx: ExecutionContext,
    ) -> None:
        """Emit tool.invoked event."""
        if not self.config.emit_events:
            return

        event = ToolInvokedEvent(
            tool_name=tool.name,
            action_id=tool_input.action_id,
            pipeline_run_id=ctx.pipeline_run_id,
            request_id=ctx.request_id,
            payload_summary=_summarize_payload(tool_input.payload),
            behavior=ctx.execution_mode,
        )
        await self._emit_event("tool.invoked", event.to_dict())

    async def _emit_tool_started(
        self,
        tool: ToolDefinition,
        tool_input: ToolInput,
        ctx: ExecutionContext,
    ) -> None:
        """Emit tool.started event."""
        if not self.config.emit_events:
            return

        event = ToolStartedEvent(
            tool_name=tool.name,
            action_id=tool_input.action_id,
            pipeline_run_id=ctx.pipeline_run_id,
            request_id=ctx.request_id,
        )
        await self._emit_event("tool.started", event.to_dict())

    async def _emit_tool_completed(
        self,
        tool: ToolDefinition,
        tool_input: ToolInput,
        ctx: ExecutionContext,
        output: ToolOutput,
        duration_ms: float,
    ) -> None:
        """Emit tool.completed event."""
        if not self.config.emit_events:
            return

        event = ToolCompletedEvent(
            tool_name=tool.name,
            action_id=tool_input.action_id,
            pipeline_run_id=ctx.pipeline_run_id,
            request_id=ctx.request_id,
            duration_ms=duration_ms,
            output_summary=_summarize_output(output),
            artifacts_count=len(output.artifacts) if output.artifacts else 0,
        )
        await self._emit_event("tool.completed", event.to_dict())

    async def _emit_tool_failed(
        self,
        tool: ToolDefinition,
        tool_input: ToolInput,
        ctx: ExecutionContext,
        error: Exception,
        duration_ms: float,
    ) -> None:
        """Emit tool.failed event."""
        if not self.config.emit_events:
            return

        event = ToolFailedEvent(
            tool_name=tool.name,
            action_id=tool_input.action_id,
            pipeline_run_id=ctx.pipeline_run_id,
            request_id=ctx.request_id,
            duration_ms=duration_ms,
            error_code=type(error).__name__,
            error_message=str(error),
        )
        await self._emit_event("tool.failed", event.to_dict())

    async def _emit_tool_denied(
        self,
        tool: ToolDefinition,
        tool_input: ToolInput,
        ctx: ExecutionContext,
        reason: str,
    ) -> None:
        """Emit tool.denied event."""
        if not self.config.emit_events:
            return

        event = ToolDeniedEvent(
            tool_name=tool.name,
            action_id=tool_input.action_id,
            pipeline_run_id=ctx.pipeline_run_id,
            request_id=ctx.request_id,
            reason=reason,
            behavior=ctx.execution_mode,
            allowed_behaviors=tool.allowed_behaviors,
        )
        await self._emit_event("tool.denied", event.to_dict())

    async def _emit_tool_undone(
        self,
        tool: ToolDefinition,
        action_id: UUID,
        ctx: ExecutionContext,
        metadata: UndoMetadata,
        duration_ms: float,
    ) -> None:
        """Emit tool.undone event."""
        if not self.config.emit_events:
            return

        event = ToolUndoneEvent(
            tool_name=tool.name,
            action_id=action_id,
            pipeline_run_id=ctx.pipeline_run_id,
            request_id=ctx.request_id,
            duration_ms=duration_ms,
            original_action_timestamp=metadata.created_at,
        )
        await self._emit_event("tool.undone", event.to_dict())

    async def _emit_tool_undo_failed(
        self,
        tool: ToolDefinition,
        action_id: UUID,
        ctx: ExecutionContext,
        error: Exception,
    ) -> None:
        """Emit tool.undo_failed event."""
        if not self.config.emit_events:
            return

        event = ToolUndoFailedEvent(
            tool_name=tool.name,
            action_id=action_id,
            pipeline_run_id=ctx.pipeline_run_id,
            request_id=ctx.request_id,
            error_message=str(error),
            reason=type(error).__name__,
        )
        await self._emit_event("tool.undo_failed", event.to_dict())

    async def _emit_approval_requested(
        self,
        tool: ToolDefinition,
        tool_input: ToolInput,
        ctx: ExecutionContext,
        request_id: UUID,
    ) -> None:
        """Emit approval.requested event."""
        if not self.config.emit_events:
            return

        event = ApprovalRequestedEvent(
            request_id=request_id,
            tool_name=tool.name,
            action_id=tool_input.action_id,
            pipeline_run_id=ctx.pipeline_run_id,
            approval_message=tool.approval_message or f"Approve {tool.name}?",
        )
        await self._emit_event("approval.requested", event.to_dict())

    async def _emit_approval_decided(
        self,
        tool: ToolDefinition,
        tool_input: ToolInput,
        ctx: ExecutionContext,
        request_id: UUID,
        granted: bool,
    ) -> None:
        """Emit approval.decided event."""
        if not self.config.emit_events:
            return

        event = ApprovalDecidedEvent(
            request_id=request_id,
            tool_name=tool.name,
            action_id=tool_input.action_id,
            pipeline_run_id=ctx.pipeline_run_id,
            decision="approved" if granted else "denied",
        )
        await self._emit_event("approval.decided", event.to_dict())

    async def _emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit an event through the event sink."""
        sink = get_event_sink()
        try:
            await sink.emit(type=event_type, data=data)
        except Exception as e:
            logger.warning(f"Failed to emit event {event_type}: {e}")


def _summarize_payload(payload: dict[str, Any], max_length: int = 200) -> dict[str, Any]:
    """Create a summary of a payload for event emission."""
    summary: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str) and len(value) > max_length:
            summary[key] = value[:max_length] + "..."
        elif isinstance(value, (list, dict)) and len(str(value)) > max_length:
            summary[key] = f"<{type(value).__name__} with {len(value)} items>"
        else:
            summary[key] = value
    return summary


def _summarize_output(output: ToolOutput) -> dict[str, Any]:
    """Create a summary of tool output for event emission."""
    return {
        "success": output.success,
        "has_data": output.data is not None,
        "has_error": output.error is not None,
        "has_artifacts": output.artifacts is not None and len(output.artifacts) > 0,
        "has_undo_metadata": output.undo_metadata is not None,
    }


__all__ = [
    "AdvancedToolExecutor",
    "ToolExecutorConfig",
    "ExecutionResult",
]
