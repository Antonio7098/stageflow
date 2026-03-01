# Projector API Reference

## Exports

```python
from stageflow.projector import (
    WSMessageProjector,
    ProjectorService,
    WSMetadata,
    WSOutboundMessage,
    WSStatusUpdatePayload,
)
```

`ProjectorService` is a backward-compatible alias of `WSMessageProjector`.

## WSMessageProjector.project

```python
project(
    message: dict[str, Any],
    *,
    connection_org_id: Any | None,
    context_request_id: Any | None,
    context_pipeline_run_id: Any | None,
) -> dict[str, Any]
```

Behavior:
- Normalizes metadata UUID fields.
- Generates UUIDs for missing/invalid request and run ids.
- Includes `org_id` only when `connection_org_id` is a valid UUID.
- For `type == "status.update"`, payload must be an object or `ValueError` is raised.

## Example

```python
from stageflow.projector import WSMessageProjector

projector = WSMessageProjector()
processed = projector.project(
    {
        "type": "status.update",
        "payload": {"service": "chat", "status": "processing"},
    },
    connection_org_id="550e8400-e29b-41d4-a716-446655440000",
    context_request_id="550e8400-e29b-41d4-a716-446655440001",
    context_pipeline_run_id="550e8400-e29b-41d4-a716-446655440002",
)
```
