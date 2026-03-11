# Agent Runtime & Prompt Safety

Stageflow now includes a reusable agent runtime in `stageflow.agent` with four built-in pieces:

- **Versioned prompt library** via `PromptTemplate` and `PromptLibrary`
- **Prompt-injection hardening** via `PromptSecurityPolicy`
- **Typed LLM output validation** via `TypedLLMOutput`
- **Functional tool loop** via `Agent` and `AgentStage`

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

`Agent` runs an LLM loop until the model emits either:

- `{"tool_calls": [...]}` to request tools, or
- `{"final_answer": "..."}` to finish

Each tool result is fed back to the model as sanitized untrusted data.

```python
from stageflow.agent import Agent, AgentConfig, AgentStage, PromptLibrary, PromptTemplate
from stageflow.api import Pipeline
from stageflow.helpers import MockLLMProvider
from stageflow.tools.base import BaseTool, ToolInput, ToolOutput
from stageflow.tools.registry import ToolRegistry

class AddTool(BaseTool):
    name = "adder"
    description = "Add two integers"
    action_type = "ADD"

    async def execute(self, input: ToolInput, ctx: dict) -> ToolOutput:
        payload = input.action.payload
        return ToolOutput(success=True, data={"sum": payload["a"] + payload["b"]})

library = PromptLibrary()
library.register(
    PromptTemplate(
        name="math-agent",
        version="v1",
        template=(
            "You are a careful math agent. Available tools:\n{tool_descriptions}\n"
            "Return JSON only."
        ),
    ),
    make_default=True,
)

registry = ToolRegistry()
registry.register(AddTool())
llm = MockLLMProvider(
    responses=[
        '{"tool_calls": [{"name": "ADD", "arguments": {"a": 2, "b": 3}}]}',
        '{"final_answer": "The sum is 5"}',
    ]
)

agent = Agent(
    llm_client=llm,
    config=AgentConfig(model="mock"),
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

## Recommended Production Pattern

1. Put your system prompts in a `PromptLibrary`
2. Version them explicitly (`v1`, `2026-03-11`, etc.)
3. Keep `PromptSecurityPolicy` enabled for both user and tool content
4. Use `TypedLLMOutput` for any structured model contract
5. Wrap the runtime in `AgentStage` when you want it inside a Stageflow DAG

## Testing

Recommended test layers:

- **Unit**: prompt rendering, security blocking, JSON extraction, retry behavior
- **Integration**: tool loop with `MockLLMProvider`
- **Smoke**: a real provider call using your production-style client wiring

See `tests/unit/test_agent_runtime.py` and `tests/integration/test_agent_stage.py` for concrete examples.