# Observability API Reference

## Protocols

```python
from stageflow.observability import (
    PipelineRunLogger,
    ProviderCallLogger,
    CircuitBreaker,
    CircuitBreakerOpenError,
)
```

### CircuitBreaker methods

```python
async is_open(*, operation: str, provider: str) -> bool
async record_success(*, operation: str, provider: str) -> None
async record_failure(*, operation: str, provider: str, reason: str) -> None
```

## Canonical envelope helpers

```python
from stageflow.observability import (
    EVENT_VERSION,
    EventKind,
    build_metadata,
    build_payload,
    infer_event_kind,
)
```

- `EVENT_VERSION`: Current envelope version constant (`"v1"`)
- `EventKind`: Enum of high-level categories (`TRACE`, `SPAN`, `GENERATION`, `TOOL`, `AGENT`, `EVALUATOR`)
- `build_payload(event_type, ctx, data)`: Returns a canonical event payload with taxonomy and correlation fields
- `build_metadata(ctx)`: Returns the metadata envelope for a given context
- `infer_event_kind(event_type)`: Maps an event name to an `EventKind`

## Telemetry ingestion and repository

```python
from stageflow.observability import (
    TelemetryIngestionService,
    TelemetryRepository,
    TelemetryEvent,
    InMemoryTelemetryRepository,
)
```

### TelemetryIngestionService

Implements `EventSink` with batching, sampling, and queue backpressure.

```python
sink = TelemetryIngestionService(
    repository=InMemoryTelemetryRepository(),
    max_batch_size=100,
    max_queue_size=1000,
    sample_rate=1.0,
)
await sink/start()
await sink.stop()
```

### TelemetryRepository protocol

```python
def store(self, event: TelemetryEvent) -> None
def store_batch(self, events: Sequence[TelemetryEvent]) -> int
def list_events(self, *, event_name: str | None = None) -> list[TelemetryEvent]
def get_agent_graph_data(self, *, trace_id: str) -> list[AgentGraphNode]
def get_user_metrics(self) -> list[UserMetric]
```

### TelemetryEvent

Pydantic model for normalized events. All fields are optional except `event_name`, `event_kind`, `event_version`, and `timestamp`.

## Dashboard helpers

```python
from stageflow.observability import (
    ObservabilityDashboard,
    build_graph_availability,
    serialize_agent_graph,
    serialize_user_metrics,
)
```

### ObservabilityDashboard

```python
dashboard = ObservabilityDashboard(repository)

graph = dashboard.get_agent_graph_view(trace_id="...")
timeline = dashboard.get_pipeline_timeline(trace_id="...")
providers = dashboard.get_provider_metrics()
insights = dashboard.get_user_insights()
```

- `get_agent_graph_view`: Returns Langfuse-compatible `AgentGraphNode` dicts for a trace
- `get_pipeline_timeline`: Returns stage timeline entries with status and duration
- `get_provider_metrics`: Returns provider/model call/error counts
- `get_user_insights`: Returns per-user observation/trace/event-kind counts

### Utility helpers

- `build_graph_availability(nodes)`: Returns `True` if graphable observations or steps are present
- `serialize_agent_graph(nodes)`: Converts `AgentGraphNode` objects to dicts
- `serialize_user_metrics(metrics)`: Converts `UserMetric` objects to dicts

## Utility functions

```python
from stageflow.observability import (
    summarize_pipeline_error,
    error_summary_to_string,
    error_summary_to_stages_patch,
    get_circuit_breaker,
    set_correlation_id,
    get_correlation_id,
    ensure_correlation_id,
    clear_correlation_id,
    get_trace_context_dict,
    get_trace_id,
    get_span_id,
)
```

## BufferedExporter stats

`BufferedExporter.stats` includes:
- `buffer_size`
- `max_buffer_size`
- `dropped_count`
- `fill_ratio`
- `high_water_warned`

## Example

```python
from stageflow.helpers import BufferedExporter, ConsoleExporter

exporter = BufferedExporter(ConsoleExporter())
stats = exporter.stats
```
