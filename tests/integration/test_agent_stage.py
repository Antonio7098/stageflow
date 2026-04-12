from __future__ import annotations

import asyncio
from typing import Any

from stageflow.agent import Agent, AgentConfig, AgentStage
from stageflow.api import Pipeline
from stageflow.helpers import MockLLMProvider
from stageflow.tools.base import BaseTool, ToolInput, ToolOutput
from stageflow.tools.registry import ToolRegistry


class AddTool(BaseTool):
    name = "adder"
    description = "Add two integers"
    action_type = "ADD"

    async def execute(self, input: ToolInput, ctx: dict[str, Any]) -> ToolOutput:  # noqa: ARG002
        payload = input.action.payload
        return ToolOutput(success=True, data={"sum": payload["a"] + payload["b"]})

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        }


class NativeToolProvider:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "messages": [dict(message) for message in messages],
                "model": model,
                **kwargs,
            }
        )
        return self._responses.pop(0)


def test_pipeline_runs_agent_stage_with_tool_loop() -> None:
    async def _run() -> None:
        llm = MockLLMProvider(
            responses=[
                '{"tool_calls": [{"name": "ADD", "arguments": {"a": 2, "b": 3}}]}',
                '{"final_answer": "The sum is 5"}',
            ]
        )
        registry = ToolRegistry()
        registry.register(AddTool())
        agent = Agent(llm_client=llm, config=AgentConfig(model="mock"), tool_registry=registry)
        pipeline = Pipeline().with_stage("agent", AgentStage(agent))

        results = await pipeline.run(input_text="what is 2 + 3?")
        output = results["agent"]

        assert output.data["response"] == "The sum is 5"
        assert output.data["iterations"] == 2
        assert output.data["tool_results"][0]["data"] == {"sum": 5}

    asyncio.run(_run())


def test_pipeline_runs_agent_stage_with_native_tool_calling() -> None:
    async def _run() -> None:
        llm = NativeToolProvider(
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
                                        "id": "call_add",
                                        "type": "function",
                                        "function": {
                                            "name": "ADD",
                                            "arguments": '{"a": 2, "b": 3}',
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
                            "message": {"role": "assistant", "content": "The sum is 5"},
                        }
                    ],
                },
            ]
        )
        registry = ToolRegistry()
        registry.register(AddTool())
        agent = Agent(llm_client=llm, config=AgentConfig(model="mock"), tool_registry=registry)
        pipeline = Pipeline().with_stage("agent", AgentStage(agent))

        results = await pipeline.run(input_text="what is 2 + 3?")
        output = results["agent"]

        assert output.data["response"] == "The sum is 5"
        assert output.data["iterations"] == 2
        assert output.data["tool_calling_mode"] == "native"
        assert output.data["tool_results"][0]["data"] == {"sum": 5}
        assert llm.calls[0]["tools"][0]["function"]["name"] == "ADD"

    asyncio.run(_run())
