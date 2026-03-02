# Duplex Systems

Duplex systems model bidirectional flows in a single pipeline: one lane for
`A -> B` and another for `B -> A`.

In Stageflow, use `DuplexLaneSpec`, `DuplexSystemSpec`, and `with_duplex_system`
to define that topology with minimal boilerplate.

## When to Use Duplex Topology

Use this pattern when both directions are first-class:

- Real-time chat transport (uplink and downlink)
- Voice systems (ingress audio vs egress audio)
- Sync bridges between two services
- Request/response paths that need independent transforms

## Core Types

```python
from stageflow.pipeline import (
    DuplexLaneSpec,
    DuplexSystemSpec,
    PipelineBuilder,
    with_duplex_system,
)
```

- `DuplexLaneSpec`: linear stage chain for one direction.
- `DuplexSystemSpec`: forward lane + reverse lane + optional join stage.
- `with_duplex_system(...)`: applies both lanes to a `PipelineBuilder`.

## Structured Builder Example

```python
from stageflow.pipeline import (
    DuplexLaneSpec,
    DuplexSystemSpec,
    PipelineBuilder,
    with_duplex_system,
)

builder = (
    PipelineBuilder("duplex_transport")
    .with_stage("ingress_a", IngressAStage())
    .with_stage("ingress_b", IngressBStage())
)

system = DuplexSystemSpec(
    forward=DuplexLaneSpec(
        stages=(
            ("uplink_decode", UplinkDecodeStage()),
            ("uplink_transform", UplinkTransformStage()),
            ("uplink_emit", UplinkEmitStage()),
        ),
        depends_on=("ingress_a",),
    ),
    reverse=DuplexLaneSpec(
        stages=(
            ("downlink_decode", DownlinkDecodeStage()),
            ("downlink_transform", DownlinkTransformStage()),
            ("downlink_emit", DownlinkEmitStage()),
        ),
        depends_on=("ingress_b",),
    ),
    join_stage=("duplex_sync", DuplexSyncStage()),
    join_depends_on=("audit",),  # Optional extra dependency
)

pipeline = with_duplex_system(builder, system)
graph = pipeline.build()
```

### Dependency Behavior

- First stage in each lane depends on lane `depends_on`.
- Subsequent stages depend on the previous stage in that lane.
- `join_stage` depends on both lane tails plus `join_depends_on`.

## Fluent Builder Example

```python
from stageflow.pipeline import FluentPipelineBuilder

pipeline = (
    FluentPipelineBuilder("duplex_chat")
    .stage("ingress", IngressStage())
    .duplex(
        forward=(
            ("uplink_parse", UplinkParseStage()),
            ("uplink_send", UplinkSendStage()),
        ),
        reverse=(
            ("downlink_parse", DownlinkParseStage()),
            ("downlink_send", DownlinkSendStage()),
        ),
        join_stage=("sync_metrics", SyncMetricsStage()),
    )
    .build()
)
```

If `forward_depends_on` / `reverse_depends_on` are omitted, fluent mode uses
the previous fluent stage as dependency for both first lane stages.

You can also explicitly control dependencies:

```python
pipeline = (
    FluentPipelineBuilder("explicit_deps")
    .stage("source_a", SourceAStage())
    .stage("source_b", SourceBStage())
    .duplex(
        forward=(
            ("uplink", UplinkStage()),
        ),
        reverse=(
            ("downlink", DownlinkStage()),
        ),
        forward_depends_on=("source_a",),  # Explicit dependency
        reverse_depends_on=("source_b",),  # Explicit dependency
        join_stage=("sync", SyncStage()),
    )
    .build()
)
```

## Duplex Without Join Stage

The `join_stage` is optional. Omit it when lanes should run independently:

```python
system = DuplexSystemSpec(
    forward=DuplexLaneSpec(
        stages=(("request_path", RequestStage()),),
        depends_on=("ingress",),
    ),
    reverse=DuplexLaneSpec(
        stages=(("response_path", ResponseStage()),),
        depends_on=("egress",),
    ),
    # No join_stage - lanes run independently
)

graph = with_duplex_system(builder, system).build()
```

## Validation and Safety

`with_duplex_system(...)` fails fast when:

- Any lane has zero stages.
- Stage names are duplicated across lanes/join.
- A duplex stage name collides with an existing builder stage.

This avoids accidental graph corruption and hard-to-debug stage overwrites.

## Testing Pattern

Test the builder (before `.build()`) to verify dependency wiring:

```python
result = with_duplex_system(builder, system)

# Test on PipelineBuilder result, not StageGraph
assert result.stages["uplink_0"].dependencies == ("ingress_a",)
assert result.stages["uplink_1"].dependencies == ("uplink_0",)
assert result.stages["downlink_0"].dependencies == ("ingress_b",)
assert result.stages["sync"].dependencies == ("uplink_1", "downlink_1")
```

Or with the fluent builder:

```python
pipeline = (
    FluentPipelineBuilder("test")
    .stage("entry", EntryStage())
    .duplex(
        forward=(("fwd", FwdStage()),),
        reverse=(("rev", RevStage()),),
        join_stage=("sync", SyncStage()),
    )
)

builder = pipeline.builder
assert builder.stages["fwd"].dependencies == ("entry",)
assert builder.stages["rev"].dependencies == ("entry",)
assert builder.stages["sync"].dependencies == ("fwd", "rev")
```

Keep business logic tests in stage-specific test modules and keep duplex tests
focused on DAG shape.
