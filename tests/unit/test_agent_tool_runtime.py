from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from stageflow import stage
from stageflow.agent import (
    Agent,
    AgentConfig,
    AgentToolCall,
    AgentToolDescriptor,
    AgentToolExecutionResult,
    PromptSecurityPolicy,
    RegistryAgentToolRuntime,
)
from stageflow.core import StageKind, StageOutput
from stageflow.pipeline import Pipeline
from stageflow.pipeline.registry import pipeline_registry
from stageflow.agent.models import AgentToolResult
from stageflow.agent.tool_runtime import AgentToolRuntime
from stageflow.testing import create_test_stage_context
from stageflow.tools.base import BaseTool, ToolInput, ToolOutput
from stageflow.tools.lifecycle import InMemoryToolLifecycleSink, SequencedToolLifecycleSink
from stageflow.tools.registry import ToolRegistry
from tests.utils.mocks import MockEventSink


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo input text"
    action_type = "ECHO"

    async def execute(self, input: ToolInput, ctx: dict[str, Any]) -> ToolOutput:
        return ToolOutput(success=True, data={"echo": input.action.payload["text"], "ctx": ctx})


class NativeProvider:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self._responses.pop(0)


class UpdateTool(BaseTool):
    name = "update"
    description = "Emit tool updates"
    action_type = "UPDATE"

    async def execute(self, input: ToolInput, ctx: dict[str, Any]) -> ToolOutput:  # noqa: ARG002
        await input.publish_update({"progress": 0.5, "step": "halfway"})
        return ToolOutput(success=True, data={"done": True})


class SubpipelineTool(BaseTool):
    name = "subpipeline"
    description = "Spawn child pipeline"
    action_type = "SUBPIPE"

    async def execute(self, input: ToolInput, ctx: dict[str, Any]) -> ToolOutput:  # noqa: ARG002
        child_run = await input.spawn_subpipeline(pipeline_name="agent_runtime_child_pipeline")
        return ToolOutput(
            success=True,
            data={"child_run_id": str(child_run.child_run_id)},
            child_runs=[child_run],
        )


class FailingTool(BaseTool):
    name = "failing"
    description = "Fail explicitly"
    action_type = "FAIL"

    async def execute(self, input: ToolInput, ctx: dict[str, Any]) -> ToolOutput:  # noqa: ARG002
        return ToolOutput(success=False, error="tool failed")


def test_registry_runtime_emits_full_tool_lifecycle_events() -> None:
    async def _run() -> None:
        provider = NativeProvider(
            responses=[
                {
                    "model": "native-model",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "ECHO",
                                            "arguments": '{"text": "hello"}',
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                },
                {
                    "model": "native-model",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "done"},
                        }
                    ],
                },
            ]
        )
        registry = ToolRegistry()
        registry.register(EchoTool())
        event_sink = MockEventSink()
        ctx = create_test_stage_context(input_text="please use a tool", event_sink=event_sink)
        agent = Agent(llm_client=provider, config=AgentConfig(model="mock"), tool_registry=registry)

        result = await agent.run("please use a tool", stage_context=ctx)

        assert result.response == "done"
        event_types = [event["type"] for event in event_sink.events]
        assert "agent.tool.requested" in event_types
        assert "agent.tool.started" in event_types
        assert "agent.tool.completed" in event_types
        assert event_types.index("agent.tool.requested") < event_types.index("agent.tool.started")
        assert event_types.index("agent.tool.started") < event_types.index("agent.tool.completed")

    import asyncio

    asyncio.run(_run())


@dataclass
class FakeToolRuntime(AgentToolRuntime):
    executed_batches: int = 0

    def has_tools(self) -> bool:
        return True

    def describe_tools(self) -> list[AgentToolDescriptor]:
        return [AgentToolDescriptor(name="ECHO", description="Fake runtime tool")]

    def provider_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "ECHO",
                    "description": "Fake runtime tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    async def execute_tool_calls(
        self,
        tool_calls: list[AgentToolCall],
        *,
        raw_tool_calls: list[dict[str, Any]] | None,  # noqa: ARG002
        stage_context: Any,  # noqa: ARG002
        tool_calling_mode: str,
        security_policy: PromptSecurityPolicy,
    ) -> AgentToolExecutionResult:
        self.executed_batches += 1
        result = AgentToolResult(
            call_id=tool_calls[0].call_id or "call_runtime",
            name=tool_calls[0].name,
            success=True,
            data={"handled_by": "custom_runtime"},
        )
        message, report = security_policy.build_native_tool_message(
            tool_name=result.name,
            call_id=result.call_id,
            payload=result.model_dump(),
        )
        assert tool_calling_mode == "native"
        return AgentToolExecutionResult(
            tool_results=[result],
            new_messages=[message],
            security_reports=[report],
        )


def test_agent_accepts_custom_tool_runtime() -> None:
    async def _run() -> None:
        provider = NativeProvider(
            responses=[
                {
                    "model": "native-model",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_runtime",
                                        "type": "function",
                                        "function": {"name": "ECHO", "arguments": "{}"},
                                    }
                                ],
                            },
                        }
                    ],
                },
                {
                    "model": "native-model",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "done"},
                        }
                    ],
                },
            ]
        )
        runtime = FakeToolRuntime()
        agent = Agent(llm_client=provider, config=AgentConfig(model="mock"), tool_runtime=runtime)

        result = await agent.run("please use a tool")

        assert result.response == "done"
        assert result.tool_results[0].data == {"handled_by": "custom_runtime"}
        assert runtime.executed_batches == 1

    import asyncio

    asyncio.run(_run())


def test_agent_rejects_ambiguous_runtime_configuration() -> None:
    with pytest.raises(ValueError):
        Agent(
            llm_client=object(),
            tool_runtime=FakeToolRuntime(),
            lifecycle_hooks=object(),  # type: ignore[arg-type]
        )


def test_registry_runtime_surfaces_tool_updates() -> None:
    async def _run() -> None:
        provider = NativeProvider(
            responses=[
                {
                    "model": "native-model",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_update",
                                        "type": "function",
                                        "function": {"name": "UPDATE", "arguments": "{}"},
                                    }
                                ],
                            },
                        }
                    ],
                },
                {
                    "model": "native-model",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "done"},
                        }
                    ],
                },
            ]
        )
        registry = ToolRegistry()
        registry.register(UpdateTool())
        event_sink = MockEventSink()
        ctx = create_test_stage_context(input_text="please update", event_sink=event_sink)
        agent = Agent(llm_client=provider, config=AgentConfig(model="mock"), tool_registry=registry)

        result = await agent.run("please update", stage_context=ctx)

        assert result.response == "done"
        assert event_sink.has_event("tool.updated")
        assert event_sink.has_event("agent.tool.updated")
        updated_event = next(event for event in event_sink.events if event["type"] == "agent.tool.updated")
        assert updated_event["data"]["payload"] == {"progress": 0.5, "step": "halfway"}

    import asyncio

    asyncio.run(_run())


def test_registry_runtime_surfaces_child_run_lineage() -> None:
    async def _run() -> None:
        pipeline_name = "agent_runtime_child_pipeline"
        async def _child_stage(_ctx: Any) -> StageOutput:
            return StageOutput.ok(data={"value": "child"})

        child_pipeline = Pipeline.from_stages(
            stage("child_stage", _child_stage, StageKind.WORK),
            name=pipeline_name,
        )
        pipeline_registry.register(pipeline_name, child_pipeline)
        provider = NativeProvider(
            responses=[
                {
                    "model": "native-model",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_subpipe",
                                        "type": "function",
                                        "function": {"name": "SUBPIPE", "arguments": "{}"},
                                    }
                                ],
                            },
                        }
                    ],
                },
                {
                    "model": "native-model",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "done"},
                        }
                    ],
                },
            ]
        )
        registry = ToolRegistry()
        registry.register(SubpipelineTool())
        event_sink = MockEventSink()
        ctx = create_test_stage_context(input_text="spawn child", event_sink=event_sink)
        agent = Agent(llm_client=provider, config=AgentConfig(model="mock"), tool_registry=registry)

        result = await agent.run("spawn child", stage_context=ctx)

        assert result.response == "done"
        assert len(result.tool_results[0].child_runs) == 1
        child_run = result.tool_results[0].child_runs[0]
        assert child_run["pipeline_name"] == pipeline_name
        assert child_run["success"] is True
        assert event_sink.has_event("pipeline.spawned_child")
        assert event_sink.has_event("tool.updated")
        tool_update = next(event for event in event_sink.events if event["type"] == "tool.updated")
        assert tool_update["data"]["update"]["payload"]["child_run"]["pipeline_name"] == pipeline_name

    import asyncio
    asyncio.run(_run())


def test_registry_runtime_emits_failed_tool_events() -> None:
    async def _run() -> None:
        provider = NativeProvider(
            responses=[
                {
                    "model": "native-model",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_fail",
                                        "type": "function",
                                        "function": {"name": "FAIL", "arguments": "{}"},
                                    }
                                ],
                            },
                        }
                    ],
                },
                {
                    "model": "native-model",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "handled"},
                        }
                    ],
                },
            ]
        )
        registry = ToolRegistry()
        registry.register(FailingTool())
        event_sink = MockEventSink()
        ctx = create_test_stage_context(input_text="fail", event_sink=event_sink)
        agent = Agent(llm_client=provider, config=AgentConfig(model="mock"), tool_registry=registry)

        result = await agent.run("fail", stage_context=ctx)

        assert result.response == "handled"
        assert result.tool_results[0].success is False
        assert event_sink.has_event("agent.tool.failed")

    import asyncio

    asyncio.run(_run())


def test_registry_runtime_persists_lifecycle_events_in_order() -> None:
    async def _run() -> None:
        provider = NativeProvider(
            responses=[
                {
                    "model": "native-model",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_update",
                                        "type": "function",
                                        "function": {"name": "UPDATE", "arguments": "{}"},
                                    }
                                ],
                            },
                        }
                    ],
                },
                {
                    "model": "native-model",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "done"},
                        }
                    ],
                },
            ]
        )
        registry = ToolRegistry()
        registry.register(UpdateTool())
        sink = InMemoryToolLifecycleSink()
        runtime = RegistryAgentToolRuntime(
            registry,
            lifecycle_sink=SequencedToolLifecycleSink(sink),
        )
        ctx = create_test_stage_context(input_text="please update")
        agent = Agent(llm_client=provider, config=AgentConfig(model="mock"), tool_runtime=runtime)

        result = await agent.run("please update", stage_context=ctx)

        assert result.response == "done"
        assert [event.event_type for event in sink.events] == [
            "tool.requested",
            "tool.started",
            "tool.updated",
            "tool.completed",
        ]
        assert [event.sequence for event in sink.events] == [1, 2, 3, 4]
        assert sink.events[2].payload["update"]["payload"] == {"progress": 0.5, "step": "halfway"}

    import asyncio

    asyncio.run(_run())
