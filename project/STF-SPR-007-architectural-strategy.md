# STF-SPR-007: Architectural Strategy Document

**Status**: Draft
**Created**: 2026-01-13
**Scope**: Core framework evolution addressing fail-fast semantics, routing, metadata, diffs, and stage categorization

---

## Executive Summary

This document analyzes twelve architectural questions raised during codebase review. Each question is evaluated against SOLID principles and observability requirements, producing concrete recommendations that preserve Stageflow's power while maintaining generality and modularity.

**Key Decisions:**
1. Introduce opt-in non-blocking execution modes without breaking fail-fast default
2. Formalize router as first-class pipeline primitive with explicit subpipeline spawning
3. Define provider metadata protocol for uniform observability across LLM backends
4. Elevate `StageKind` from annotation to behavioral discriminator where useful
5. Keep direct-dependency-only access as architectural invariant

---

## 1. Fail-Fast vs Fire-and-Forget

### Current State
```python
# dag.py:402-417 - Blocking fail-fast only
if task.exception():
    for t in active_tasks:
        t.cancel()
    raise task.exception()
```

All stage failures immediately cancel siblings and propagate. No non-blocking modes exist.

### Analysis

| Mode | Behavior | Use Case |
|------|----------|----------|
| **fail-fast-blocking** (current) | Exception cancels all, pipeline raises | Critical paths, transactional work |
| **fail-fast-non-blocking** | Exception cancels all, caller notified async | Background pipelines with failure interest |
| **fire-and-forget** | Exception logged, siblings continue | Analytics, telemetry, non-critical enrichment |
| **fire-and-forget-with-callback** | Exception triggers callback, siblings continue | Alerting on optional stage failure |

### SOLID Evaluation

- **SRP**: Execution strategy is a single responsibility separate from DAG topology
- **OCP**: New modes should extend executor, not modify core loop
- **LSP**: All modes must honor `StageOutput` contract
- **ISP**: Stages shouldn't know execution mode; executor handles
- **DIP**: Executor depends on abstract `ExecutionStrategy`, not concrete modes

### Recommendation

Introduce `ExecutionMode` enum and strategy pattern:

```python
class ExecutionMode(Enum):
    FAIL_FAST_BLOCKING = "fail_fast_blocking"      # Current default
    FAIL_FAST_ASYNC = "fail_fast_async"            # Non-blocking with failure signal
    CONTINUE_ON_ERROR = "continue_on_error"        # Log and continue
    CONTINUE_WITH_CALLBACK = "continue_callback"   # Callback on failure, continue

@dataclass
class ExecutionConfig:
    mode: ExecutionMode = ExecutionMode.FAIL_FAST_BLOCKING
    on_stage_error: Callable[[str, Exception], Awaitable[None]] | None = None
    error_policy: dict[str, ExecutionMode] = field(default_factory=dict)  # Per-stage override
```

**Observability**: Each mode emits `stage.error` event with `execution_mode` and `action_taken` fields.

---

## 2. Router Architecture

### Current State
Router is a convention: ordinary stages with `StageKind.ROUTE` that output routing decisions. Downstream stages read decisions via `ctx.inputs.get()`.

### Analysis

**Question**: Should router be outside the pipeline? Its own pipeline? Spawn subpipelines?

| Approach | Pros | Cons |
|----------|------|------|
| **Router as stage** (current) | Simple, composable, testable | No automatic subpipeline dispatch |
| **Router as orchestrator** | Explicit control flow | Breaks pipeline abstraction, harder to test |
| **Router + auto-dispatch** | Clean separation | Magic behavior, debugging harder |
| **Router as meta-pipeline** | Type-safe routing | Over-engineering for most cases |

### Recommendation

Keep router as stage but formalize the **Router-Dispatcher pattern**:

```python
@dataclass
class RoutingDecision:
    """Structured output from router stages."""
    selected_route: str
    confidence: float = 1.0
    fallback_route: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

class RouterStage(Protocol):
    kind: ClassVar[StageKind] = StageKind.ROUTE

    async def execute(self, ctx: StageContext) -> StageOutput:
        """Must return StageOutput with route field containing RoutingDecision."""
        ...

class DispatcherStage:
    """Consumes RoutingDecision and spawns appropriate subpipeline."""

    ROUTE_PIPELINES: dict[str, str] = {
        "fast_path": "fast_pipeline",
        "slow_path": "deep_analysis_pipeline",
    }

    async def execute(self, ctx: StageContext) -> StageOutput:
        decision: RoutingDecision = ctx.inputs.get_typed("router", RoutingDecision)
        pipeline_name = self.ROUTE_PIPELINES.get(decision.selected_route)

        result = await ctx.spawner.spawn(
            pipeline_name,
            correlation_id=ctx.correlation_id,
            parent_stage_id=self.name,
        )
        return StageOutput.ok(subpipeline_result=result)
```

**Key Principle**: Router decides, Dispatcher acts. Separation enables:
- Testing routing logic independently
- Reusing dispatchers across pipelines
- Observability: routing decisions logged before dispatch

NOTES: i think this is overcomplicating
---

## 3. Topology in Context

### Current State
```python
# context_snapshot.py:86-88
topology: str | None = None  # e.g., "fast_kernel", "accurate_kernel"
execution_mode: str | None = None  # e.g., "practice", "roleplay"
```

Used for logging and event correlation, not execution decisions.

### Analysis

**Question**: Do we need topology? Do we need it at all?

| Role | Current Use | Potential Use |
|------|-------------|---------------|
| **Observability** | Pipeline identification in logs | Required |
| **Service extraction** | `extract_service(topology)` helper | Useful |
| **Execution branching** | Not used | Anti-pattern |
| **Metrics partitioning** | Implicit via pipeline name | Could formalize |

### Recommendation

**Keep topology but clarify its role as observability-only:**

```python
@dataclass
class TopologyInfo:
    """Observability metadata, not execution control."""

    pipeline_name: str                    # Required: identifies the pipeline
    kernel: str | None = None             # Optional: logical grouping
    execution_mode: str | None = None     # Optional: behavioral variant
    environment: str | None = None        # Optional: prod/staging/dev

    def to_otel_attributes(self) -> dict[str, str]:
        """Export as OpenTelemetry resource attributes."""
        return {k: v for k, v in asdict(self).items() if v is not None}
```

**Anti-pattern to avoid:**
```python
# BAD: Using topology for execution decisions
if ctx.topology == "fast_kernel":
    skip_validation = True  # Should be explicit stage config, not topology

NOTE: is topology not just the pipeline? the name of the pipeline?
```

---

## 4. Provider Metadata Protocol

### Current State
```python
# groq_client.py - Discards metadata
async def chat(...) -> str:
    response = await self.client.chat.completions.create(...)
    return response.choices[0].message.content or ""  # usage field lost
```

### Analysis

LLM providers return rich metadata (tokens, latency, model version, rate limits). Current approach discards this, breaking observability.

### Recommendation

Define `ProviderResponse` protocol that all wrappers must return:

```python
@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_tokens: int = 0

@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Standardized response from any LLM provider."""

    content: str
    usage: TokenUsage
    model: str
    provider: str
    latency_ms: float

    # Provider-specific metadata
    raw_response: Any = None           # Full response for debugging
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)

    # Rate limit info (when available)
    rate_limit_remaining: int | None = None
    rate_limit_reset_ms: int | None = None

# Updated Groq wrapper
async def chat(...) -> ProviderResponse:
    start = time.monotonic()
    response = await self.client.chat.completions.create(...)
    latency = (time.monotonic() - start) * 1000

    return ProviderResponse(
        content=response.choices[0].message.content or "",
        usage=TokenUsage(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
        ),
        model=response.model,
        provider="groq",
        latency_ms=latency,
        raw_response=response,
        finish_reason=response.choices[0].finish_reason,
    )
```

**Observability Integration:**
```python
# Automatic logging via ProviderCallLogger protocol
await logger.log_call_end(
    call_id=call_id,
    success=True,
    latency_ms=response.latency_ms,
    input_tokens=response.usage.input_tokens,
    output_tokens=response.usage.output_tokens,
    model=response.model,
    provider=response.provider,
)

NOTES: what stt? tts? any other kind of provier? is this general enough?
```

---

## 5. Subpipeline Spawning

### Current State
Explicit via `SubpipelineSpawner.spawn()` with depth limits, context forking, and correlation tracking.

### Analysis

Current design is sound. The question "should router spawn subpipelines?" conflates two responsibilities.

### Recommendation

**Formalize the pattern with helper:**

```python
class SubpipelineDispatcher:
    """Utility for common routing-to-subpipeline pattern."""

    def __init__(self, spawner: SubpipelineSpawner, route_map: dict[str, str]):
        self._spawner = spawner
        self._route_map = route_map

    async def dispatch(
        self,
        routing_decision: RoutingDecision,
        ctx: PipelineContext,
        parent_stage_id: str,
    ) -> SubpipelineResult:
        pipeline = self._route_map.get(routing_decision.selected_route)
        if not pipeline and routing_decision.fallback_route:
            pipeline = self._route_map.get(routing_decision.fallback_route)

        if not pipeline:
            raise RoutingError(f"No pipeline for route: {routing_decision.selected_route}")

        return await self._spawner.spawn(
            pipeline,
            ctx=ctx,
            correlation_id=ctx.correlation_id,
            parent_stage_id=parent_stage_id,
            topology=routing_decision.selected_route,  # Observability
        )

NOTES: is this really necessary?
```

---

## 6. Diffs and Undos

### Current State
```python
# tools/diff.py
class DiffType(Enum):
    UNIFIED = "unified"
    CONTEXT = "context"
    JSON_PATCH = "json_patch"
    LINE_BY_LINE = "line_by_line"

# tools/undo.py
class UndoStore:
    async def store(action_id, tool_name, undo_data, ttl_seconds)
    async def get(action_id) -> UndoMetadata | None
```

### Analysis

**Question**: "Native diffs" vs helpers? How to deal with diffs and undos?

The current approach is correct: diffs and undos are tool-level concerns, not framework concerns. The framework provides utilities; tools compose them.

### Recommendation

**Strengthen the pattern with a unified interface:**

```python
@dataclass
class ReversibleChange:
    """Captures a change that can be undone."""

    action_id: str
    tool_name: str
    diff: DiffResult
    undo_data: dict[str, Any]
    created_at: datetime
    ttl_seconds: int = 3600

    async def store(self, undo_store: UndoStore) -> None:
        await undo_store.store(
            self.action_id,
            self.tool_name,
            {"diff": self.diff.to_dict(), **self.undo_data},
            self.ttl_seconds,
        )

class ReversibleToolMixin:
    """Mixin for tools that produce reversible changes."""

    async def execute_reversible(
        self,
        input: ToolInput,
        compute_change: Callable[[ToolInput], Awaitable[tuple[Any, ReversibleChange]]],
    ) -> ToolOutput:
        result, change = await compute_change(input)
        await change.store(self.undo_store)

        return ToolOutput.ok(
            data=result,
            undo_metadata={"action_id": change.action_id},
        )
```

**Key Insight**: "Native" diffs don't need to exist. All diffs are computed, and the framework should provide composable utilities rather than special-casing diff handling.

---

## 7. Tool Call Parsing

### Current State
No framework-level tool call parsing. Application-specific, handled in agent stages.

### Analysis

This is correct. Tool call formats vary by provider (OpenAI function calling, Anthropic tool_use, custom grammars). Framework should not impose parsing logic.

### Recommendation

**Provide optional parsing utilities, not mandates:**

```python
class ToolCallParser(Protocol):
    """Protocol for tool call parsing strategies."""

    def parse(self, response: ProviderResponse) -> list[ParsedToolCall]:
        """Extract tool calls from provider response."""
        ...

@dataclass
class ParsedToolCall:
    """Normalized tool call representation."""

    id: str
    name: str
    arguments: dict[str, Any]
    raw: Any = None  # Original format for debugging

# Built-in parsers (optional)
class OpenAIToolCallParser(ToolCallParser):
    def parse(self, response: ProviderResponse) -> list[ParsedToolCall]:
        return [
            ParsedToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=json.loads(tc.function.arguments),
                raw=tc,
            )
            for tc in response.tool_calls
        ]

class AnthropicToolCallParser(ToolCallParser):
    def parse(self, response: ProviderResponse) -> list[ParsedToolCall]:
        # Handle Anthropic's tool_use content blocks
        ...
```

**Usage in stages:**
```python
class AgentStage:
    def __init__(self, parser: ToolCallParser = OpenAIToolCallParser()):
        self._parser = parser

    async def execute(self, ctx: StageContext) -> StageOutput:
        response = await self.llm.chat(messages, tools=self.tools)
        tool_calls = self._parser.parse(response)
        # Execute tool calls...

NOTES: but we have a tool registry. can we not connect it to the tool registry? we will have the name of the tool, then match to the registry.
```

---

## 8. StageKind Purpose

### Current State
```python
class StageKind(str, Enum):
    TRANSFORM = "transform"  # STT, TTS, LLM
    ENRICH = "enrich"        # Profile, Memory, Skills
    ROUTE = "route"          # Router, Dispatcher
    GUARD = "guard"          # Guardrails, Policy
    WORK = "work"            # Assessment, Triage, Persist
    AGENT = "agent"          # Coach, Interviewer
```

Currently semantic only. Used for registry categorization and testing strategies.

### Analysis

**Question**: Does StageKind serve any function for tool parsing, execution, diffs?

Currently: No. It's purely descriptive.

**Should it?** Partial yes. Some behaviors naturally correlate with kinds:

| Kind | Potential Behavioral Implications |
|------|-----------------------------------|
| GUARD | Fail-fast always (security/policy) |
| ENRICH | Continue-on-error acceptable |
| ROUTE | Must produce RoutingDecision |
| AGENT | User-facing streaming enabled |

### Recommendation

**Elevate StageKind to optional behavioral discriminator:**

```python
@dataclass
class StageKindBehavior:
    """Default behaviors associated with stage kinds."""

    default_execution_mode: ExecutionMode = ExecutionMode.FAIL_FAST_BLOCKING
    requires_output_type: type | None = None
    streaming_enabled: bool = False
    telemetry_level: str = "standard"

STAGE_KIND_BEHAVIORS: dict[StageKind, StageKindBehavior] = {
    StageKind.GUARD: StageKindBehavior(
        default_execution_mode=ExecutionMode.FAIL_FAST_BLOCKING,  # Never ignore
        telemetry_level="detailed",  # Audit trail
    ),
    StageKind.ROUTE: StageKindBehavior(
        requires_output_type=RoutingDecision,  # Type enforcement
    ),
    StageKind.AGENT: StageKindBehavior(
        streaming_enabled=True,  # User-facing
        telemetry_level="verbose",
    ),
    StageKind.ENRICH: StageKindBehavior(
        default_execution_mode=ExecutionMode.CONTINUE_ON_ERROR,  # Optional
    ),
}

NOTES: I dont think the technical overhead justifiess the value it brings.
```

**Key Principle**: Behaviors are defaults, always overridable. StageKind provides sensible conventions without constraining flexibility.

---

## 9. Recursive Dependency Checking

### Current State
```python
# dag.py:479-483 - Direct dependencies only
prior_outputs = {
    dep_name: output
    for dep_name, output in completed.items()
    if dep_name in spec.dependencies
}
```

Stages can only access outputs from explicitly declared dependencies.

### Analysis

**Question**: Should stages access outputs of indirect dependencies (A → B → C, can C access A)?

| Approach | Pros | Cons |
|----------|------|------|
| **Direct only** (current) | Explicit data flow, easier debugging | Verbose dependency declarations |
| **Transitive access** | Less boilerplate | Hidden dependencies, harder to trace |
| **Opt-in transitive** | Flexibility | Complexity, inconsistent patterns |

### Recommendation

**Keep direct-only as architectural invariant.** This is a feature, not a limitation.

**Rationale:**
1. **SOLID (DIP)**: Explicit dependencies make coupling visible
2. **Testability**: Each stage's inputs are explicit
3. **Observability**: Data flow graphs are accurate
4. **Refactoring**: Moving/removing stages has predictable impact

**If transitive access is needed**, the pattern is explicit forwarding:

```python
class StageB:
    dependencies = ("stage_a",)

    async def execute(self, ctx: StageContext) -> StageOutput:
        a_output = ctx.inputs.from_stage("stage_a")
        return StageOutput.ok(
            b_result=...,
            forwarded_from_a=a_output.get("needed_field"),  # Explicit forwarding
        )

class StageC:
    dependencies = ("stage_b",)  # Only declares B, but gets A's data via B

    async def execute(self, ctx: StageContext) -> StageOutput:
        b_output = ctx.inputs.from_stage("stage_b")
        a_field = b_output.get("forwarded_from_a")  # Explicit, traceable

NOTES: is there a difference between explicit dependencies and defining what rns where in the pipeline? explicit dependencies uses outputs from another stage. but dependencies are supposed to just define the dag. having the extra deps will mess up visual representations of dag. what si the best approach here??
```

---

## 10. User-Facing vs Internal Streaming

### Current State
```python
# ports.py - Streaming callbacks
@dataclass(frozen=True, slots=True)
class LLMPorts:
    send_token: Callable[[str], Awaitable[None]] | None = None

@dataclass(frozen=True, slots=True)
class AudioPorts:
    send_audio_chunk: Callable[[bytes, str, int, bool], Awaitable[None]] | None = None
```

Streaming is callback-based. No explicit "user-facing" marker.

### Analysis

The distinction matters for:
1. **Buffering**: Internal tool calls don't need real-time streaming
2. **Error handling**: User-facing errors need sanitization
3. **Telemetry**: User-facing latency is critical metric
4. **Cancellation**: User disconnect should cancel user-facing, not internal

### Recommendation

**Formalize streaming context:**

```python
class StreamingMode(Enum):
    USER_FACING = "user_facing"      # Real-time to user, latency-critical
    INTERNAL = "internal"            # Buffered, can batch
    BACKGROUND = "background"        # Fire-and-forget, low priority

@dataclass
class StreamingContext:
    """Context for streaming operations."""

    mode: StreamingMode
    send_token: Callable[[str], Awaitable[None]] | None = None
    send_audio: Callable[[bytes, str, int, bool], Awaitable[None]] | None = None

    # User-facing specific
    user_disconnected: asyncio.Event | None = None
    sanitize_errors: bool = True

    async def stream_token(self, token: str) -> None:
        if self.user_disconnected and self.user_disconnected.is_set():
            raise UserDisconnectedError()

        if self.send_token:
            await self.send_token(token)

    def with_mode(self, mode: StreamingMode) -> "StreamingContext":
        """Create child context with different mode."""
        return replace(self, mode=mode)
```

**Usage:**
```python
class AgentStage:
    async def execute(self, ctx: StageContext) -> StageOutput:
        # User-facing: stream response tokens
        async for token in self.llm.stream_chat(messages):
            await ctx.streaming.stream_token(token)

        # Internal: tool execution doesn't stream
        internal_ctx = ctx.streaming.with_mode(StreamingMode.INTERNAL)
        tool_result = await self.execute_tool(tool_call, internal_ctx)

NOTES: what about when there is an internal section and a user facing one in the same llm response??
```

---

## Summary: Implementation Priorities

### Phase 1: Foundation (High Impact, Low Risk)
1. **ProviderResponse protocol** - Fixes metadata loss, enables observability
2. **RoutingDecision type** - Formalizes router output contract
3. **StreamingContext** - Explicit user-facing vs internal separation

### Phase 2: Execution Modes (Medium Impact, Medium Risk)
4. **ExecutionMode enum + strategy** - Non-blocking/continue-on-error support
5. **StageKindBehavior defaults** - Sensible conventions per kind

### Phase 3: Developer Experience (Lower Priority)
6. **ReversibleToolMixin** - Standardized diff/undo pattern
7. **ToolCallParser protocol** - Optional parsing utilities
8. **SubpipelineDispatcher** - Routing helper

### Invariants (Do Not Change)
- Direct dependency access only
- Fail-fast-blocking as default
- Topology for observability only
- Tools are synchronous, streaming is callback-based

---

## Appendix: SOLID Checklist

| Principle | Application |
|-----------|-------------|
| **SRP** | ExecutionMode separate from DAG topology; ProviderResponse separate from stage logic |
| **OCP** | New execution modes extend via strategy pattern; new providers implement protocol |
| **LSP** | All ProviderResponse implementations interchangeable; all StageOutput contracts honored |
| **ISP** | Stages don't know execution mode; tools don't know streaming mode |
| **DIP** | Depend on ToolCallParser protocol, not concrete parsers; depend on UndoStore protocol |

---

## Appendix: Observability Requirements

Every recommendation includes observability hooks:

| Feature | Events/Metrics |
|---------|---------------|
| ExecutionMode | `stage.error` with `action_taken` field |
| RoutingDecision | `pipeline.route` with decision metadata |
| ProviderResponse | Token counts, latency, model, provider as span attributes |
| StreamingContext | `stream.token`, `stream.disconnect` events |
| ReversibleChange | `tool.change`, `tool.undo` with diff metadata |
