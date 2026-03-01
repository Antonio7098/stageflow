# Protocols API Reference

## ExecutionContext

```python
from stageflow.protocols import ExecutionContext
```

Required interface:
- `pipeline_run_id`
- `request_id`
- `execution_mode`
- `to_dict()`
- `try_emit_event(type, data)`

### Minimal `PipelineContext` example

```python
from uuid import uuid4
from stageflow import PipelineContext

ctx = PipelineContext(
    pipeline_run_id=uuid4(),
    request_id=uuid4(),
    session_id=uuid4(),
    user_id=uuid4(),
    org_id=uuid4(),
    interaction_id=uuid4(),
    execution_mode="practice",
)
```

### Streaming helpers example

```python
from stageflow.helpers import ChunkQueue, StreamingBuffer, BufferedExporter

queue = ChunkQueue(event_emitter=ctx.try_emit_event)
buffer = StreamingBuffer(event_emitter=ctx.try_emit_event)
exporter = BufferedExporter(exporter=my_exporter)
```

## EventSink

```python
from stageflow.protocols import EventSink
```

- `async emit(*, type, data)`
- `try_emit(*, type, data)`

## RunStore

```python
from stageflow.protocols import RunStore
```

- `create_run(...)`
- `update_status(run_id, status, *, error=None, duration_ms=None, **data)`
- `get_run(run_id)`

## ConfigProvider

```python
from stageflow.protocols import ConfigProvider
```

- `get(key, default=None)`

## CorrelationIds

```python
from stageflow.protocols import CorrelationIds
```

- `to_dict()` converts IDs to event/log payload form.
