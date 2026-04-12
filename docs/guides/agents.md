# Agent Runtime & Prompt Safety

Stageflow now includes a reusable agent runtime in `stageflow.agent` with four built-in pieces:

- **Versioned prompt library** via `PromptTemplate` and `PromptLibrary`
- **Prompt-injection hardening** via `PromptSecurityPolicy`
- **Typed LLM output validation** via `TypedLLMOutput`
- **Functional tool loop** via `Agent` and `AgentStage`

The tool loop is now split into two framework layers:

- `Agent` owns turn orchestration, provider calls, and prompt safety
- `AgentToolRuntime` owns tool schema export, tool-call execution, reinjection messages, and lifecycle hooks

## Core Building Blocks

### Versioned prompts

Use `PromptLibrary` to register multiple versions of a prompt and render them with metadata.

```python
from stageflow.agent import PromptLibrary, PromptTemplate

library = PromptLibrary()
library.register(
    PromptTemplate(
        name="support-agent",
        version="v1",
        template="You are a support agent. Tools:\n{tool_descriptions}",
    ),
    make_default=True,
)
rendered = library.render("support-agent", variables={"tool_descriptions": "- LOOKUP: fetch data"})
```

### Prompt security

`PromptSecurityPolicy` adds layered protections before user content or tool output is injected into the next model turn.

- Detects common prompt-injection phrases using `InjectionDetector`
- Neutralizes control-like tokens such as `<system>` and `[SYSTEM]`
- Truncates oversized user input or tool results
- Wraps user/tool content as **untrusted data** before it reaches the model

By default, suspicious **user** input is blocked and suspicious **tool** output is sanitized but not blocked.

### Typed validation with retries

Use `TypedLLMOutput` to require JSON output that validates against a Pydantic model. If the model responds with prose, markdown fences, or malformed JSON, Stageflow retries with corrective feedback.

```python
from pydantic import BaseModel
from stageflow.agent import TypedLLMOutput

class Answer(BaseModel):
    final_answer: str

typed = TypedLLMOutput(Answer)
result = await typed.generate(client, [{"role": "user", "content": "Say hi as JSON"}], model="mock")
print(result.parsed.final_answer)
```

## Functional Tool Loop

`Agent` now prefers provider-native tool calling when the client exposes
`chat(...)` and tools are registered. In that mode, Stageflow sends provider
tool definitions up front, executes returned tool calls, and feeds the
sanitized results back as `role="tool"` messages.

The default runtime is `RegistryAgentToolRuntime`, but you can inject a custom
`AgentToolRuntime` when the host application needs different execution,
projection, or persistence behavior.

If the client does not support native tools, the runtime falls back to the
older JSON loop where the model emits either:

- `{"tool_calls": [...]}` to request tools, or
- `{"final_answer": "..."}` to finish

```python
from stageflow.agent import Agent, AgentConfig, AgentStage, PromptLibrary, PromptTemplate
from stageflow.api import Pipeline
from stageflow.tools.base import BaseTool, ToolInput, ToolOutput
from stageflow.tools.registry import ToolRegistry

class AddTool(BaseTool):
    name = "adder"
    description = "Add two integers"
    action_type = "ADD"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        }

    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        payload = input.action.payload
        return ToolOutput(success=True, data={"sum": payload["a"] + payload["b"]})


class NativeToolClient:
    async def chat(self, *, messages, model, tools=None, tool_choice=None, **kwargs):
        ...

library = PromptLibrary()
library.register(
    PromptTemplate(
        name="math-agent",
        version="v1",
        template=(
            "You are a careful math agent. Available tools:\n{tool_descriptions}\n"
            "Use native tool calling when available."
        ),
    ),
    make_default=True,
)

registry = ToolRegistry()
registry.register(AddTool())
llm = NativeToolClient()

agent = Agent(
    llm_client=llm,
    config=AgentConfig(model="mock", tool_calling_mode="auto"),
    prompt_library=library,
    prompt_name="math-agent",
    tool_registry=registry,
)

pipeline = Pipeline().with_stage("agent", AgentStage(agent))
results = await pipeline.run(input_text="What is 2 + 3?")
print(results["agent"].data["response"])
```

## Provider Contract

The runtime accepts clients with either:

- `async def chat(*, messages, model, **kwargs)`
- `async def complete(prompt, *, messages, model, **kwargs)`

The returned object can be a plain string, a dict, `LLMResponse`, or any object with `content`, `model`, and optional `usage` fields.

When native tool calling is active, Stageflow also passes:

- `tools=[...]` with provider function definitions
- `tool_choice="auto"`

Use `AgentConfig(tool_calling_mode="json")` to force the JSON loop, or
`"native"` to require provider-native tools.

## Typed Tool Contracts

Tools can now expose a typed input model instead of hand-written JSON Schema:

```python
from pydantic import BaseModel
from stageflow.tools import BaseTool, ToolInput, ToolOutput

class AddArgs(BaseModel):
    a: int
    b: int

class AddTool(BaseTool):
    name = "adder"
    description = "Add two integers"
    action_type = "ADD"
    input_model = AddArgs

    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        payload = input.action.payload
        return ToolOutput(success=True, data={"sum": payload["a"] + payload["b"]})
```

Stageflow derives the provider schema from `input_model` and validates raw
provider tool-call arguments before execution. Invalid arguments are surfaced as
unresolved tool calls instead of being silently coerced.

## Tool Updates And Child Runs

`ToolInput` now exposes runtime helpers for long-running tools:

- `await input.publish_update({...})`
- `await input.spawn_subpipeline(pipeline_name="...")`

The default registry-backed runtime converts these into observable
`tool.updated` and `agent.tool.updated` events, and child pipeline lineage is
captured on the final `tool_results[].child_runs` payload.

## Recommended Production Pattern

1. Put your system prompts in a `PromptLibrary`
2. Version them explicitly (`v1`, `2026-03-11`, etc.)
3. Keep `PromptSecurityPolicy` enabled for both user and tool content
4. Use `TypedLLMOutput` for any structured model contract
5. Use typed tool inputs (`input_model`) for provider-native tool safety
6. Use `ToolInput.publish_update()` for long-running tools instead of ad hoc side channels
7. Use `run_logged_pipeline(...)` or `run_logged_subpipeline(...)` when the agent sits inside a production workflow that needs run logs and lineage
8. Wrap the runtime in `AgentStage` when you want it inside a Stageflow DAG

## Testing

Recommended test layers:

- **Unit**: prompt rendering, security blocking, JSON extraction, retry behavior
- **Integration**: native tool loop with a `chat(...)` client plus JSON fallback with `MockLLMProvider`
- **Smoke**: a real provider call using your production-style client wiring

See `tests/unit/test_agent_runtime.py`, `tests/unit/test_agent_tool_runtime.py`, and
`tests/integration/test_agent_stage.py` for concrete examples.

For an opt-in real-provider smoke test, run:

```bash
STAGEFLOW_SMOKE_OPENAI_API_KEY=... \
STAGEFLOW_SMOKE_OPENAI_MODEL=... \
pytest -q tests/smoke/test_native_tool_runtime_smoke.py
```

You can point it at an OpenAI-compatible endpoint by also setting
`STAGEFLOW_SMOKE_OPENAI_BASE_URL`.
