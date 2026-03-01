"""Stageflow helper utilities.

This package provides reusable helpers for common pipeline patterns:

- memory: Chat memory management stages
- guardrails: Content filtering and policy enforcement
- streaming: Streaming primitives for audio/real-time
- analytics: Analytics export adapters
- mocks: Mock providers for testing (LLM, STT, TTS, auth)
- run_utils: Pipeline execution and logging utilities
- uuid_utils: UUID collision detection and telemetry
- memory_tracker: Runtime memory growth tracking
- compression: Delta compression utilities for context payloads
"""

from stageflow.helpers.analytics import (
    AnalyticsEvent,
    AnalyticsExporter,
    AnalyticsSink,
    BufferedExporter,
    ConsoleExporter,
    JSONFileExporter,
)
from stageflow.helpers.guardrails import (
    ContentFilter,
    ContentLengthCheck,
    GuardrailCheck,
    GuardrailConfig,
    GuardrailResult,
    GuardrailStage,
    InjectionDetector,
    PIIDetector,
    PolicyViolation,
    ViolationType,
)
from stageflow.helpers.memory import (
    InMemoryStore,
    MemoryConfig,
    MemoryEntry,
    MemoryFetchStage,
    MemoryStore,
    MemoryWriteStage,
)
from stageflow.helpers.memory_tracker import MemorySample, MemoryTracker, track_memory
from stageflow.helpers.mocks import (
    MockAuthProvider,
    MockLLMProvider,
    MockSTTProvider,
    MockToolExecutor,
    MockTTSProvider,
)
from stageflow.helpers.providers import (
    LLMResponse,
    STTResponse,
    TTSResponse,
)
from stageflow.helpers.run_utils import (
    ObservableEventSink,
    PipelineRunner,
    RunResult,
    run_simple_pipeline,
    setup_logging,
)
from stageflow.helpers.streaming import (
    AudioChunk,
    AudioFormat,
    BackpressureMonitor,
    ChunkQueue,
    StreamConfig,
    StreamingBuffer,
    encode_audio_for_logging,
)
from stageflow.helpers.timestamps import (
    detect_unix_precision,
    normalize_to_utc,
    parse_timestamp,
)
from stageflow.helpers.uuid_utils import (
    ClockSkewDetector,
    UuidCollisionMonitor,
    UuidEvent,
    UuidEventListener,
    generate_uuid7,
)

__all__ = [
    # Memory
    "MemoryConfig",
    "MemoryEntry",
    "MemoryFetchStage",
    "MemoryStore",
    "MemoryWriteStage",
    "InMemoryStore",
    # Guardrails
    "GuardrailConfig",
    "GuardrailResult",
    "GuardrailStage",
    "PIIDetector",
    "InjectionDetector",
    "ContentFilter",
    "PolicyViolation",
    "ViolationType",
    "GuardrailCheck",
    "ContentLengthCheck",
    # Streaming
    "ChunkQueue",
    "StreamingBuffer",
    "BackpressureMonitor",
    "AudioChunk",
    "AudioFormat",
    "StreamConfig",
    "encode_audio_for_logging",
    # Analytics
    "AnalyticsEvent",
    "AnalyticsExporter",
    "AnalyticsSink",
    "JSONFileExporter",
    "ConsoleExporter",
    "BufferedExporter",
    # Mocks
    "MockLLMProvider",
    "MockSTTProvider",
    "MockTTSProvider",
    "MockAuthProvider",
    "MockToolExecutor",
    # Run utils
    "ObservableEventSink",
    "PipelineRunner",
    "RunResult",
    "run_simple_pipeline",
    "setup_logging",
    # Providers
    "LLMResponse",
    "STTResponse",
    "TTSResponse",
    # Timestamp helpers
    "parse_timestamp",
    "detect_unix_precision",
    "normalize_to_utc",
    # Runtime helpers
    "UuidCollisionMonitor",
    "UuidEvent",
    "UuidEventListener",
    "ClockSkewDetector",
    "generate_uuid7",
    "MemoryTracker",
    "MemorySample",
    "track_memory",
]
