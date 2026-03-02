# Real-Time LLM to TTS Streaming

This example demonstrates stage-to-stage real-time handoff:

`LLMStreamStage` publishes incremental text chunks while `TTSStreamStage`
consumes them concurrently through `RealtimeStageBus`.

## Topology

```text
[llm_stream] ---> (channel: llm_to_tts) ---> [tts_stream]
```

Both stages can run at the same time. The producer closes the channel when done.

## Complete Example

```python
import asyncio
from uuid import uuid4

from stageflow import Pipeline, PipelineContext, PipelineTimer, StageContext, StageKind, StageOutput
from stageflow.helpers import RealtimeStageBus
from stageflow.stages.inputs import create_stage_inputs
from stageflow.stages.ports import create_core_ports


class LLMStreamStage:
    name = "llm_stream"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        bus = ctx.inputs.ports.realtime_bus
        if bus is None:
            return StageOutput.fail(error="Missing realtime_bus in ports")

        prompt = ctx.snapshot.input_text or "hello from stageflow"
        # Simulate model token streaming
        for token in (prompt.split(" ") + ["<eos>"]):
            await bus.publish("llm_to_tts", token)
            await asyncio.sleep(0.02)

        await bus.close_channel("llm_to_tts")
        return StageOutput.ok(streamed_tokens=True)


class TTSStreamStage:
    name = "tts_stream"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        bus = ctx.inputs.ports.realtime_bus
        if bus is None:
            return StageOutput.fail(error="Missing realtime_bus in ports")

        synthesized_chunks = []
        async for token in bus.subscribe("llm_to_tts"):
            if token == "<eos>":
                break
            # Replace with real incremental TTS synthesis call
            synthesized_chunks.append(f"AUDIO({token})")

        return StageOutput.ok(audio_chunks=synthesized_chunks, chunk_count=len(synthesized_chunks))


async def run_demo() -> None:
    pipeline = (
        Pipeline(name="realtime_llm_tts")
        .with_stage("llm_stream", LLMStreamStage, StageKind.TRANSFORM)
        .with_stage(
            "tts_stream",
            TTSStreamStage,
            StageKind.TRANSFORM,
            dependencies=("llm_stream",),
        )
    )
    graph = pipeline.build()

    pipeline_ctx = PipelineContext(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=uuid4(),
        interaction_id=uuid4(),
        topology="realtime_llm_tts",
        execution_mode="demo",
        input_text="stream this text in real time",
    )

    # For advanced port wiring, derive a stage context from PipelineContext.
    snapshot = pipeline_ctx.to_snapshot()
    bus = RealtimeStageBus(default_max_size=128)
    ports = create_core_ports(realtime_bus=bus)
    inputs = create_stage_inputs(snapshot, ports=ports)
    root_stage_ctx = StageContext(
        snapshot=snapshot,
        inputs=inputs,
        stage_name="pipeline_entry",
        timer=PipelineTimer(),
    )

    # Execute through the Stageflow graph.
    results = await graph.run(root_stage_ctx)
    print("LLM status:", results["llm_stream"].status)
    print("TTS chunks:", results["tts_stream"].data["audio_chunks"])

    # Optional: close any remaining channels if you created multiple channels.
    await bus.close_all()


if __name__ == "__main__":
    asyncio.run(run_demo())
```

## Notes

- Channel naming (`llm_to_tts`) should be stable and explicit.
- If your use case is quality-sensitive, keep queue overflow blocking (default).
- For low-latency UI streaming, consider overflow-drop mode and monitor bus stats.
