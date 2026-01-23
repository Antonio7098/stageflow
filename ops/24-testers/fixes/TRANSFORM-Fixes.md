# TRANSFORM Stage Data Processing & Fusion Tracker

## Scope
Synthesizes TRANSFORM-001, TRANSFORM-004, TRANSFORM-005 findings covering multimodal data fusion, timestamp extraction/normalization, and large payload chunking strategies.

---

## Evidence Summary

| Report | Core Claim | Code Evidence | Verdict |
|--------|------------|---------------|---------|
| TRANSFORM-001 | No built-in multimodal fusion stage | `StageKind.TRANSFORM` exists (`@stageflow/core/stage_enums.py:13`) but no `MultimodalFusionStage` in helpers. | **Confirmed gap** |
| TRANSFORM-001 | Excellent streaming audio primitives | `ChunkQueue`, `StreamingBuffer`, `BackpressureMonitor` in `@stageflow/helpers/__init__.py:90-94`. | **Confirmed strength** |
| TRANSFORM-001 | Error messages lack modality context | `StageOutput.fail(error=...)` accepts string only, no structured modality metadata. | **Confirmed gap** |
| TRANSFORM-004 | RFC 2822 timestamp parsing fails | No timestamp utilities in core. Custom implementation required. | **Confirmed gap** |
| TRANSFORM-004 | Unix timestamp overflow for milliseconds | Python `datetime.fromtimestamp()` fails for 13+ digit timestamps. | **Confirmed bug** |
| TRANSFORM-005 | Semantic chunking exceeds size limits | Custom implementation issue, not framework bug. | **Implementation gap** |
| TRANSFORM-005 | ChunkAssembler doesn't detect missing chunks | Custom implementation returns success despite missing chunks. | **Implementation gap** |
| TRANSFORM-005 | `emit_event` vs `try_emit_event` API mismatch | `StageContext` has `event_sink.try_emit()`, not `ctx.emit_event()`. | **Confirmed DX issue** |

---

## Consolidated Findings

### Critical Issues (P0)

**None** - All issues are reliability/DX gaps, not breaking bugs.

### High-Severity Issues (P1)

| ID | Issue | Impact | Evidence |
|----|-------|--------|----------|
| BUG-032 | Unix timestamp precision ambiguity causes overflow | Cannot process millisecond/microsecond timestamps | TRANSFORM-004: OverflowError for 13+ digits |
| BUG-034 | ChunkAssembler doesn't detect missing chunks | Silent data loss in reassembly | TRANSFORM-005: Success with missing chunk 2 |
| DX-036 | `emit_event` method doesn't exist | All pipeline tests fail initially | TRANSFORM-005: AttributeError |

### Medium-Severity Issues

| ID | Issue | Impact |
|----|-------|--------|
| BUG-031 | RFC 2822 timestamp parsing fails | Cannot extract from email/HTTP headers |
| BUG-033 | Semantic chunking exceeds size limits | Chunks larger than specified limit |
| DX-032 | Error messages lack modality context | Debugging multimodal pipelines harder |
| DX-035 | Missing timestamp handling documentation | Developers must research patterns externally |
| DX-037 | StageContext timer parameter required | Unclear from docs |

### Strengths

| ID | Strength | Evidence |
|----|----------|----------|
| STR-048 | Excellent streaming audio primitives | Built baseline audio pipeline in <30 min |
| STR-051 | Excellent ISO 8601 parsing accuracy | 93.3% success rate |

---

## Implementation Plan

### Phase 1: Bug Fixes (Immediate)

| # | Status | Action | Priority | Effort | Impact |
|---|--------|--------|----------|--------|--------|
| 1 | ✅ Completed | **Fix Unix timestamp precision** - Added `stageflow.helpers.timestamps.detect_unix_precision()` with digit-count scaling (10=seconds, 13=milliseconds, 16=microseconds) before `datetime.fromtimestamp()`. | P0 | Low | High |
| 2 | ✅ Completed | **Add RFC 2822 parsing** - `parse_timestamp()` now delegates to `email.utils.parsedate_to_datetime()` with UTC normalization, plus tests covering GMT examples. | P1 | Low | High |
| 3 | ✅ Completed | **Document `try_emit_event`** - Docs updated to show `ctx.try_emit_event()`/`ctx.event_sink.try_emit()` instead of the non-existent `ctx.emit_event()`, covering StageContext API and streaming helpers. | P0 | Low | High |

### Phase 2: Documentation & DX (Short Term)

| # | Status | Action | Owner | Effort |
|---|--------|--------|-------|--------|
| 1 | Not Started | **Multimodal Fusion Cookbook** - Add `docs/examples/multimodal-fusion.md` with image+text+audio patterns | Docs | Medium |
| 2 | Not Started | **Timestamp Handling Guide** - Add `docs/guides/timestamps.md` with ISO 8601, RFC 2822, Unix epoch patterns | Docs | Low |
| 3 | Not Started | **Chunking Patterns Guide** - Add `docs/advanced/chunking.md` with fixed-size, semantic, recursive strategies | Docs | Low |
| 4 | Not Started | **Error Context Enhancement** - Document pattern for modality-specific error metadata in `StageOutput.fail()` | Docs | Low |

### Phase 3: Core Runtime Enhancements (Medium Term)

| # | Status | Enhancement | Priority | Design |
|---|--------|-------------|----------|--------|
| 1 | Not Started | **Structured Error Metadata** | P1 | Extend `StageOutput.fail()` to accept `metadata: dict` for modality context, stack traces, remediation hints. |
| 2 | Not Started | **Timestamp Utilities** | P2 | Add `stageflow.helpers.timestamps` module with `parse_timestamp()`, `normalize_to_utc()`, `detect_format()`. |
| 3 | Not Started | **Chunking Utilities** | P2 | Add `stageflow.helpers.chunking` module with `fixed_size_chunk()`, `semantic_chunk()`, `assemble_chunks()`. |

### Phase 4: Stageflow Plus Components (Medium Term)

| ID | Status | Component | Type | Priority | Use Case |
|----|--------|-----------|------|----------|----------|
| IMP-048 | Not Started | `MultimodalFusionStage` | Stagekind | P0 | Combine text, audio, image modalities into unified context |
| IMP-049 | Not Started | Image processing helpers | Utility | P2 | Image encoding/decoding, resizing, format conversion |
| IMP-052 | Not Started | `TimestampExtractStage` | Stagekind | P1 | Common timestamp parsing with format detection |
| IMP-053 | Not Started | `ChunkingStage` | Stagekind | P1 | Configurable chunking with size enforcement |
| - | Not Started | `UnixTimestampStage` | Stagekind | P1 | Epoch handling with precision detection |
| - | Not Started | `ChunkAssemblerStage` | Stagekind | P1 | Reassembly with missing chunk detection |
| - | Not Started | `ImageProcessingStage` | Stagekind | P1 | Image encoding/decoding stages |
| - | Not Started | `CrossModalitySecurityGuard` | Guard | P1 | Unified validation across modalities |

---

## Design Principles

### Speed
- Timestamp parsing: <1ms per timestamp (confirmed)
- Chunking: 15.2 MB/s throughput (confirmed)
- Multimodal fusion: Parallel modality processing where independent

### Safety
- **Fail-explicit for missing chunks**: Assembler should fail, not succeed with warnings
- **Precision detection**: Prevent overflow by detecting timestamp precision before conversion
- **Size enforcement**: Semantic chunking must respect size limits or split recursively

### Observability
- Modality-specific error metadata in `StageOutput.fail()`
- Chunk tracking via metadata (sequence, checksum, total_chunks)
- Timestamp format detection logged for debugging

### Reliability
- RFC 2822 parsing handles timezone abbreviations (GMT, EST, etc.)
- Chunking checksums detect corruption
- Missing chunk detection prevents silent data loss

### SOLID Principles
- **Single Responsibility**: Each stage handles one transformation (timestamp, chunk, fuse)
- **Open/Closed**: Chunking strategies via strategy pattern, not code changes
- **Liskov Substitution**: All TRANSFORM stages implement `Stage` protocol
- **Interface Segregation**: Minimal chunking interface (chunk + assemble)
- **Dependency Inversion**: Fusion stage depends on modality abstractions, not concrete processors

### Scalability
- Chunking enables parallel processing of large payloads
- Streaming primitives handle backpressure
- Memory usage scales with chunk size, not payload size

---

## Code Evidence: Existing Infrastructure

```python
@stageflow/helpers/__init__.py:90-94
# Streaming primitives (confirmed excellent)
"ChunkQueue",
"StreamingBuffer",
"BackpressureMonitor",
"AudioChunk",
"StreamConfig",

@stageflow/core/stage_output.py
# StageOutput.fail() - string error only, no structured metadata
@classmethod
def fail(cls, error: str, ...) -> StageOutput:
    ...
```

---

## Proposed API: Timestamp Utilities

```python
# stageflow.helpers.timestamps (proposed)

def parse_timestamp(value: str | int | float) -> datetime:
    """Parse timestamp from various formats.
    
    Supports:
    - ISO 8601 (2023-10-05T14:48:00Z)
    - RFC 2822 (Thu, 05 Oct 2023 14:48:00 GMT)
    - Unix epoch (seconds, milliseconds, microseconds)
    - Human readable (October 5, 2023)
    """
    ...

def detect_unix_precision(timestamp: int) -> str:
    """Detect Unix timestamp precision.
    
    Returns: 'seconds' | 'milliseconds' | 'microseconds'
    """
    digits = len(str(abs(timestamp)))
    if digits <= 10:
        return 'seconds'
    elif digits <= 13:
        return 'milliseconds'
    else:
        return 'microseconds'

def normalize_to_utc(dt: datetime) -> datetime:
    """Normalize datetime to UTC timezone."""
    ...
```

---

## Proposed API: Chunking Stage

```python
# stageflow.plus.chunking (proposed)

class ChunkingStage:
    name = "chunking"
    kind = StageKind.TRANSFORM
    
    def __init__(
        self,
        chunk_size: int = 16384,
        strategy: str = "fixed_size",  # fixed_size, semantic, recursive
        overlap: int = 0,
        enforce_size_limit: bool = True,  # Fail if chunk exceeds size
    ):
        ...

class ChunkAssemblerStage:
    name = "assembler"
    kind = StageKind.TRANSFORM
    
    def __init__(
        self,
        validate_checksums: bool = True,
        fail_on_missing: bool = True,  # Default: fail, not warn
    ):
        ...
```

---

## Test Coverage Requirements

| Component | Test Type | Coverage Target |
|-----------|-----------|-----------------|
| Unix precision detection | Unit | 10, 13, 16 digit timestamps |
| RFC 2822 parsing | Unit | Common timezone abbreviations |
| Semantic chunking size | Unit | Chunks never exceed limit |
| Missing chunk detection | Unit | Assembler fails on gaps |
| Multimodal fusion | Integration | Image+text+audio combined |

---

## Next Actions

1. **Immediate**: Fix `try_emit_event` documentation (1 day)
2. **Immediate**: Implement Unix timestamp precision detection (1 day)
3. **This Sprint**: Add RFC 2822 parsing support (1 day)
4. **This Sprint**: Create `docs/guides/timestamps.md` (1 day)
5. **Next Sprint**: Implement `ChunkingStage` prototype with size enforcement
6. **Backlog**: Design `MultimodalFusionStage` API

---

## DX Score Summary

| Report | Score | Key Friction |
|--------|-------|--------------|
| TRANSFORM-001 | 3.6/5 | Missing multimodal fusion patterns |
| TRANSFORM-004 | 4.0/5 | Missing timestamp-specific guide |
| TRANSFORM-005 | 3.2/5 | emit_event vs try_emit_event confusion |
| **Average** | **3.6/5** | Data processing patterns underdocumented |

---

## Performance Benchmarks

| Operation | Throughput | Latency | Notes |
|-----------|------------|---------|-------|
| Timestamp parsing | ~1000/sec | 1-2ms | ISO 8601 |
| Chunking | 15.2 MB/s | N/A | Fixed-size |
| STT (mock) | N/A | ~120ms P95 | Streaming |
| TTS (mock) | N/A | ~60ms P95 | Streaming |

---

*Synthesized from TRANSFORM-001, TRANSFORM-004, TRANSFORM-005 final reports.*
