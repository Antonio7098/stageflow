# Real-Time Stage Streaming

Use this guide when one stage must stream data to another while both are running,
for example `LLM streaming -> TTS synthesis`.

Stageflow provides `RealtimeStageBus` for this pattern.

## Why a Bus

Dependency-only handoff (`ctx.inputs.get_from(...)`) is end-of-stage. For real-time
hops, you need a shared streaming channel.

`RealtimeStageBus` gives you named async channels backed by `ChunkQueue` with
backpressure and close signaling.

## Quick Start

Use the `create_realtime_stage_context` helper to wire everything up:

```python
from stageflow.helpers import create_realtime_stage_context

# Create context with bus already wired
ctx, bus = create_realtime_stage_context(snapshot)

# In your stages:
# ctx.inputs.ports.realtime_bus.publish("channel_name", item)
# async for item in ctx.inputs.ports.realtime_bus.subscribe("channel_name"):
```

## Minimal LLM -> TTS Pattern

```python
from stageflow.core import StageOutput

class LLMStreamStage:
    async def execute(self, ctx):
        bus = ctx.inputs.ports.realtime_bus
        for token in ["Hello", " ", "world", "!"]:
            await bus.publish("llm_to_tts", token)
        await bus.close_channel("llm_to_tts")
        return StageOutput.ok(streamed=True)


class TTSStreamStage:
    async def execute(self, ctx):
        bus = ctx.inputs.ports.realtime_bus
        text = []
        async for token in bus.subscribe("llm_to_tts"):
            text.append(token)
            # synthesize incremental audio here
        return StageOutput.ok(full_text="".join(text))
```

## Channel Conventions

- Use stable channel names: `llm_to_tts`, `tts_to_audio`, etc.
- Producer closes its channel when done (`close_channel`).
- Consumer reads with `async for ... in bus.subscribe(channel)`.

## Backpressure Guidance

`RealtimeStageBus` channels use `ChunkQueue`, so you can choose:

- `default_drop_on_overflow=False` to block producer (lossless)
- `default_drop_on_overflow=True` to prioritize latency over completeness

For speech systems, blocking is often better for quality; dropping can be useful
for low-latency live captions.

## Full Example

See the runnable example:

- [Real-Time LLM to TTS Streaming](../examples/realtime-llm-tts.md)
