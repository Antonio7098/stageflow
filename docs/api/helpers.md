# Helper Modules API Reference

This page documents the APIs exported by `stageflow.helpers`.

## Key exports

```python
from stageflow.helpers import (
    # Guardrails
    ViolationType,
    PolicyViolation,
    GuardrailCheck,
    ContentLengthCheck,
    GuardrailConfig,
    GuardrailResult,
    GuardrailStage,
    PIIDetector,
    InjectionDetector,
    ContentFilter,
    # Streaming
    BackpressureMonitor,
    ChunkQueue,
    StreamingBuffer,
    AudioChunk,
    AudioFormat,
    StreamConfig,
    # Analytics
    AnalyticsEvent,
    AnalyticsExporter,
    BufferedExporter,
    ConsoleExporter,
    JSONFileExporter,
)
```

## BackpressureMonitor

```python
BackpressureMonitor(*, high_water_mark: int = 80, low_water_mark: int = 20)
```

- `high_water_mark` / `low_water_mark` are percentage thresholds.
- Use `record_put(queue_size, max_size)` and `should_throttle()`.

## BufferedExporter

```python
BufferedExporter(
    exporter: AnalyticsExporter,
    *,
    batch_size: int = 100,
    flush_interval_seconds: float = 10.0,
    max_buffer_size: int = 10000,
    on_overflow: Callable[[int, int], None] | None = None,
    high_water_mark: float = 0.8,
)
```

- Constructor parameter is `exporter` (not `sink`).
- Flush interval parameter is `flush_interval_seconds`.
- `stats` returns keys:
  - `buffer_size`
  - `max_buffer_size`
  - `dropped_count`
  - `fill_ratio`
  - `high_water_warned`

## Example

```python
from stageflow.helpers import ConsoleExporter, BufferedExporter, BackpressureMonitor

exporter = BufferedExporter(ConsoleExporter(), batch_size=50, flush_interval_seconds=2.0)
monitor = BackpressureMonitor(high_water_mark=80, low_water_mark=20)
```
