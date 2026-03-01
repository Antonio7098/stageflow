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
