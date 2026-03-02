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

from stageflow import Pipeline, PipelineTimer, StageContext, StageKind, StageOutput
from stageflow.context import ContextSnapshot, RunIdentity
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
        .with_stage("tts_stream", TTSStreamStage, StageKind.TRANSFORM)
    )
    graph = pipeline.build()

    snapshot = ContextSnapshot(
        run_id=RunIdentity(
            pipeline_run_id=uuid4(),
            request_id=uuid4(),
            session_id=uuid4(),
            user_id=uuid4(),
            org_id=uuid4(),
            interaction_id=uuid4(),
        ),
        topology="realtime_llm_tts",
        execution_mode="demo",
        input_text="stream this text in real time",
    )

    bus = RealtimeStageBus(default_max_size=128)
    ports = create_core_ports(realtime_bus=bus)
    inputs = create_stage_inputs(snapshot, ports=ports, strict=False)
    ctx = StageContext(
        snapshot=snapshot,
        inputs=inputs,
        stage_name="pipeline_entry",
        timer=PipelineTimer(),
    )

    # Launch both stage runners concurrently to demonstrate real-time handoff.
    llm = LLMStreamStage()
    tts = TTSStreamStage()
    llm_task = asyncio.create_task(llm.execute(ctx))
    tts_task = asyncio.create_task(tts.execute(ctx))
    llm_out, tts_out = await asyncio.gather(llm_task, tts_task)

    print("LLM status:", llm_out.status)
    print("TTS chunks:", tts_out.data["audio_chunks"])

    # Optional: close any remaining channels if you created multiple channels.
    await bus.close_all()


if __name__ == "__main__":
    asyncio.run(run_demo())
```

## Notes

- Channel naming (`llm_to_tts`) should be stable and explicit.
- If your use case is quality-sensitive, keep queue overflow blocking (default).
- For low-latency UI streaming, consider overflow-drop mode and monitor bus stats.
