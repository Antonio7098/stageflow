"""Pluggable tool runtime abstractions for the agent loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from stageflow.tools.registry import ToolRegistry
from stageflow.tools.runtime_io import StageflowToolRuntimeIO
from stageflow.tools.schema import build_tool_input_schema

from .models import AgentToolCall, AgentToolResult
from .security import PromptSecurityPolicy, PromptSecurityReport


class AgentToolRuntimeError(RuntimeError):
    """Raised when the agent tool runtime cannot complete its work."""


@dataclass(frozen=True, slots=True)
class AgentToolDescriptor:
    """Minimal tool description used by prompts and provider contracts."""

    name: str
    description: str


@dataclass(frozen=True, slots=True)
class AgentToolExecutionResult:
    """Result of executing one batch of tool calls."""

    tool_results: list[AgentToolResult]
    new_messages: list[dict[str, Any]]
    security_reports: list[PromptSecurityReport]


class AgentLifecycleHooks(Protocol):
    """Lifecycle hooks around agent tool execution."""

    def on_tool_call_requested(
        self,
        *,
        stage_context: Any,
        tool_name: str,
        call_id: str,
        arguments: dict[str, Any],
    ) -> None:
        """Called after a tool call is accepted for execution."""

    def on_tool_call_unresolved(
        self,
        *,
        stage_context: Any,
        tool_name: str,
        call_id: str,
        error: str,
    ) -> None:
        """Called when a provider tool call cannot be resolved."""

    def on_tool_call_started(
        self,
        *,
        stage_context: Any,
        tool_name: str,
        call_id: str,
        arguments: dict[str, Any],
    ) -> None:
        """Called immediately before executing a tool."""

    def on_tool_call_completed(
        self,
        *,
        stage_context: Any,
        result: AgentToolResult,
    ) -> None:
        """Called after a tool execution completes or fails."""

    def on_tool_call_failed(
        self,
        *,
        stage_context: Any,
        result: AgentToolResult,
    ) -> None:
        """Called after a tool execution fails."""

    def on_tool_call_updated(
        self,
        *,
        stage_context: Any,
        tool_name: str,
        call_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Called when a running tool emits a structured update."""


class NoOpAgentLifecycleHooks:
    """Lifecycle hook implementation that intentionally does nothing."""

    def on_tool_call_requested(
        self,
        *,
        stage_context: Any,  # noqa: ARG002
        tool_name: str,  # noqa: ARG002
        call_id: str,  # noqa: ARG002
        arguments: dict[str, Any],  # noqa: ARG002
    ) -> None:
        return None

    def on_tool_call_unresolved(
        self,
        *,
        stage_context: Any,  # noqa: ARG002
        tool_name: str,  # noqa: ARG002
        call_id: str,  # noqa: ARG002
        error: str,  # noqa: ARG002
    ) -> None:
        return None

    def on_tool_call_started(
        self,
        *,
        stage_context: Any,  # noqa: ARG002
        tool_name: str,  # noqa: ARG002
        call_id: str,  # noqa: ARG002
        arguments: dict[str, Any],  # noqa: ARG002
    ) -> None:
        return None

    def on_tool_call_completed(
        self,
        *,
        stage_context: Any,  # noqa: ARG002
        result: AgentToolResult,  # noqa: ARG002
    ) -> None:
        return None

    def on_tool_call_failed(
        self,
        *,
        stage_context: Any,  # noqa: ARG002
        result: AgentToolResult,  # noqa: ARG002
    ) -> None:
        return None

    def on_tool_call_updated(
        self,
        *,
        stage_context: Any,  # noqa: ARG002
        tool_name: str,  # noqa: ARG002
        call_id: str,  # noqa: ARG002
        payload: dict[str, Any],  # noqa: ARG002
    ) -> None:
        return None


class EventEmittingAgentLifecycleHooks(NoOpAgentLifecycleHooks):
    """Default lifecycle hooks that emit stage-context events."""

    def on_tool_call_requested(
        self,
        *,
        stage_context: Any,
        tool_name: str,
        call_id: str,
        arguments: dict[str, Any],
    ) -> None:
        _emit(
            stage_context,
            "agent.tool.requested",
            {"tool": tool_name, "call_id": call_id, "arguments": arguments},
        )

    def on_tool_call_unresolved(
        self,
        *,
        stage_context: Any,
        tool_name: str,
        call_id: str,
        error: str,
    ) -> None:
        payload = {"tool": tool_name, "call_id": call_id, "error": error}
        _emit(stage_context, "tools.unresolved", payload)
        _emit(stage_context, "agent.tool.unresolved", payload)

    def on_tool_call_started(
        self,
        *,
        stage_context: Any,
        tool_name: str,
        call_id: str,
        arguments: dict[str, Any],
    ) -> None:
        _emit(
            stage_context,
            "agent.tool.started",
            {"tool": tool_name, "call_id": call_id, "arguments": arguments},
        )

    def on_tool_call_completed(
        self,
        *,
        stage_context: Any,
        result: AgentToolResult,
    ) -> None:
        payload = {
            "tool": result.name,
            "call_id": result.call_id,
            "success": result.success,
            "error": result.error,
        }
        _emit(stage_context, "agent.tool.executed", payload)
        _emit(stage_context, "agent.tool.completed", payload)

    def on_tool_call_failed(
        self,
        *,
        stage_context: Any,
        result: AgentToolResult,
    ) -> None:
        payload = {
            "tool": result.name,
            "call_id": result.call_id,
            "success": False,
            "error": result.error,
        }
        _emit(stage_context, "agent.tool.executed", payload)
        _emit(stage_context, "agent.tool.failed", payload)

    def on_tool_call_updated(
        self,
        *,
        stage_context: Any,
        tool_name: str,
        call_id: str,
        payload: dict[str, Any],
    ) -> None:
        _emit(
            stage_context,
            "agent.tool.updated",
            {"tool": tool_name, "call_id": call_id, "payload": payload},
        )


class AgentToolRuntime(Protocol):
    """Contract between the agent loop and concrete tool execution."""

    def has_tools(self) -> bool:
        """Return whether tools are registered for this runtime."""

    def describe_tools(self) -> list[AgentToolDescriptor]:
        """Return prompt-friendly tool descriptions."""

    def provider_tools(self) -> list[dict[str, Any]]:
        """Return provider-native tool definitions."""

    async def execute_tool_calls(
        self,
        tool_calls: list[AgentToolCall],
        *,
        raw_tool_calls: list[dict[str, Any]] | None,
        stage_context: Any,
        tool_calling_mode: str,
        security_policy: PromptSecurityPolicy,
    ) -> AgentToolExecutionResult:
        """Execute one tool-call batch and build reinjection messages."""


@dataclass(frozen=True, slots=True)
class _ToolAction:
    id: Any
    type: str
    payload: dict[str, Any]


class RegistryAgentToolRuntime:
    """Default agent tool runtime backed by ToolRegistry."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        *,
        lifecycle_hooks: AgentLifecycleHooks | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._lifecycle_hooks = lifecycle_hooks or EventEmittingAgentLifecycleHooks()

    def has_tools(self) -> bool:
        return bool(self._tool_registry.list_tools())

    def describe_tools(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name=tool.action_type,
                description=tool.description or tool.name,
            )
            for tool in self._tool_registry.list_tools()
        ]

    def provider_tools(self) -> list[dict[str, Any]]:
        provider_tools: list[dict[str, Any]] = []
        for tool in self._tool_registry.list_tools():
            provider_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.action_type,
                        "description": tool.description or tool.name,
                        "parameters": build_tool_input_schema(tool),
                    },
                }
            )
        return provider_tools

    async def execute_tool_calls(
        self,
        tool_calls: list[AgentToolCall],
        *,
        raw_tool_calls: list[dict[str, Any]] | None,
        stage_context: Any,
        tool_calling_mode: str,
        security_policy: PromptSecurityPolicy,
    ) -> AgentToolExecutionResult:
        results: list[AgentToolResult] = []
        reports: list[PromptSecurityReport] = []
        new_messages: list[dict[str, Any]] = []
        ctx_dict = stage_context.to_dict() if stage_context is not None else {}

        if raw_tool_calls:
            resolved, unresolved = self._tool_registry.parse_and_resolve(raw_tool_calls)
            for call in unresolved:
                tool_result = AgentToolResult(
                    call_id=call.call_id,
                    name=call.name,
                    success=False,
                    error=call.error,
                )
                message, report = _tool_result_message(
                    security_policy=security_policy,
                    tool_name=call.name,
                    call_id=call.call_id,
                    payload=tool_result.model_dump(),
                    tool_calling_mode=tool_calling_mode,
                )
                new_messages.append(message)
                results.append(tool_result)
                reports.append(report)
                self._lifecycle_hooks.on_tool_call_unresolved(
                    stage_context=stage_context,
                    tool_name=call.name,
                    call_id=call.call_id,
                    error=call.error,
                )

            tool_calls = [
                AgentToolCall(name=call.name, arguments=call.arguments, call_id=call.call_id)
                for call in resolved
            ]

        for call in tool_calls:
            resolved_call_id = call.call_id or str(uuid4())
            self._lifecycle_hooks.on_tool_call_requested(
                stage_context=stage_context,
                tool_name=call.name,
                call_id=resolved_call_id,
                arguments=call.arguments,
            )
            self._lifecycle_hooks.on_tool_call_started(
                stage_context=stage_context,
                tool_name=call.name,
                call_id=resolved_call_id,
                arguments=call.arguments,
            )
            action = _ToolAction(id=uuid4(), type=call.name, payload=call.arguments)
            runtime_io = StageflowToolRuntimeIO(
                stage_context=stage_context,
                tool_name=call.name,
                call_id=resolved_call_id,
                parent_stage_id=getattr(stage_context, "stage_name", "agent"),
                on_update=self._lifecycle_hooks.on_tool_call_updated,
            )
            try:
                output = await self._tool_registry.execute(action, ctx_dict, runtime=runtime_io)
                if output is None:
                    tool_result = AgentToolResult(
                        call_id=resolved_call_id,
                        name=call.name,
                        success=False,
                        error="Tool registry returned no result",
                    )
                else:
                    tool_result = AgentToolResult(
                        call_id=resolved_call_id,
                        name=call.name,
                        success=output.success,
                        data=output.data,
                        error=output.error,
                        child_runs=[child_run.to_dict() for child_run in (output.child_runs or [])],
                    )
            except Exception as exc:
                tool_result = AgentToolResult(
                    call_id=resolved_call_id,
                    name=call.name,
                    success=False,
                    error=str(exc),
                )

            message, report = _tool_result_message(
                security_policy=security_policy,
                tool_name=call.name,
                call_id=resolved_call_id,
                payload=tool_result.model_dump(),
                tool_calling_mode=tool_calling_mode,
            )
            new_messages.append(message)
            results.append(tool_result)
            reports.append(report)
            if tool_result.success:
                self._lifecycle_hooks.on_tool_call_completed(
                    stage_context=stage_context,
                    result=tool_result,
                )
            else:
                self._lifecycle_hooks.on_tool_call_failed(
                    stage_context=stage_context,
                    result=tool_result,
                )

        return AgentToolExecutionResult(
            tool_results=results,
            new_messages=new_messages,
            security_reports=reports,
        )


def _tool_result_message(
    *,
    security_policy: PromptSecurityPolicy,
    tool_name: str,
    call_id: str,
    payload: dict[str, Any],
    tool_calling_mode: str,
) -> tuple[dict[str, Any], PromptSecurityReport]:
    if tool_calling_mode == "native":
        return security_policy.build_native_tool_message(
            tool_name=tool_name,
            call_id=call_id,
            payload=payload,
        )
    return security_policy.build_tool_message(
        tool_name=tool_name,
        call_id=call_id,
        payload=payload,
    )


def _emit(stage_context: Any, event_type: str, data: dict[str, Any]) -> None:
    if stage_context is not None and hasattr(stage_context, "try_emit_event"):
        stage_context.try_emit_event(event_type, data)


__all__ = [
    "AgentLifecycleHooks",
    "AgentToolDescriptor",
    "AgentToolExecutionResult",
    "AgentToolRuntime",
    "AgentToolRuntimeError",
    "EventEmittingAgentLifecycleHooks",
    "NoOpAgentLifecycleHooks",
    "RegistryAgentToolRuntime",
]
