"""Optional real-provider smoke test for native agent tool calling.

This test is intentionally opt-in. It runs only when the following env vars are set:

- ``STAGEFLOW_SMOKE_OPENAI_API_KEY``
- ``STAGEFLOW_SMOKE_OPENAI_MODEL``

Optional:
- ``STAGEFLOW_SMOKE_OPENAI_BASE_URL`` (defaults to ``https://api.openai.com/v1``)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

import pytest

from stageflow.agent import Agent, AgentConfig
from stageflow.helpers.providers import LLMResponse
from stageflow.tools import BaseTool, ToolInput, ToolOutput, ToolRegistry


class AddTool(BaseTool):
    name = "adder"
    description = "Add two integers"
    action_type = "ADD"

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

    async def execute(self, input: ToolInput, ctx: dict[str, Any]) -> ToolOutput:  # noqa: ARG002
        payload = input.action.payload
        return ToolOutput(success=True, data={"sum": payload["a"] + payload["b"]})


class OpenAICompatibleSmokeClient:
    def __init__(self, *, api_key: str, model: str, base_url: str) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Any,  # noqa: ARG002
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model or self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        request = urllib.request.Request(
            url=f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - network path
            body = exc.read().decode("utf-8", errors="replace")
            raise AssertionError(f"Smoke provider call failed: {exc.code} {body}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        choice = raw["choices"][0]
        message = choice.get("message", {})
        tool_calls: list[dict[str, Any]] = []
        for call in message.get("tool_calls", []) or []:
            function = call.get("function", {}) or {}
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments) if arguments else {}
            tool_calls.append(
                {
                    "id": call.get("id"),
                    "call_id": call.get("id"),
                    "name": function.get("name"),
                    "arguments": arguments,
                }
            )

        usage = raw.get("usage", {}) or {}
        return LLMResponse(
            content=message.get("content") or "",
            model=raw.get("model") or model or self._model,
            provider="openai-compatible-smoke",
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
            finish_reason=choice.get("finish_reason"),
            tool_calls=tool_calls,
            raw_response=raw,
        )


@pytest.mark.asyncio
async def test_native_tool_runtime_against_real_provider() -> None:
    api_key = os.getenv("STAGEFLOW_SMOKE_OPENAI_API_KEY")
    model = os.getenv("STAGEFLOW_SMOKE_OPENAI_MODEL")
    if not api_key or not model:
        pytest.skip("Set STAGEFLOW_SMOKE_OPENAI_API_KEY and STAGEFLOW_SMOKE_OPENAI_MODEL to run")

    base_url = os.getenv("STAGEFLOW_SMOKE_OPENAI_BASE_URL", "https://api.openai.com/v1")
    client = OpenAICompatibleSmokeClient(api_key=api_key, model=model, base_url=base_url)

    registry = ToolRegistry()
    registry.register(AddTool())
    agent = Agent(
        llm_client=client,
        config=AgentConfig(model=model, tool_calling_mode="native", max_turns=3),
        tool_registry=registry,
    )

    result = await agent.run(
        "Use the ADD tool to compute 2 + 3. Call the tool instead of doing arithmetic in assistant text."
    )

    assert result.tool_calling_mode == "native"
    assert result.tool_results, "Provider did not return a tool call"
    assert result.tool_results[0].success is True
    assert result.tool_results[0].data == {"sum": 5}
    assert "5" in result.response
