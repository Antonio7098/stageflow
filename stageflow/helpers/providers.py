"""Provider response types for LLM, STT, and TTS providers.

This module provides standardized response dataclasses for different provider types.
Each provider type has its own response class with relevant metadata fields.

Usage:
    from stageflow.helpers.providers import LLMResponse, STTResponse, TTSResponse

    # LLM response with token usage
    response = LLMResponse(
        content="Hello!",
        model="gpt-4",
        provider="openai",
        input_tokens=10,
        output_tokens=5,
        latency_ms=150.0,
    )

    # STT response with confidence
    response = STTResponse(
        text="Hello world",
        confidence=0.95,
        duration_ms=1500.0,
        language="en",
    )

    # TTS response with audio metadata
    response = TTSResponse(
        audio=audio_bytes,
        duration_ms=2000.0,
        sample_rate=16000,
        format="pcm_16",
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Standardized response from LLM providers.

    Captures content, token usage, and provider metadata for observability.

    Attributes:
        content: The generated text content.
        model: Model identifier used for generation.
        provider: Provider name (e.g., "openai", "anthropic", "groq").
        input_tokens: Number of input/prompt tokens.
        output_tokens: Number of output/completion tokens.
        latency_ms: Request latency in milliseconds.
        finish_reason: Why generation stopped (e.g., "stop", "length").
        tool_calls: List of tool calls if any.
        cached_tokens: Number of tokens served from cache (if supported).
        raw_response: Original provider response for debugging.
    """

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    cached_tokens: int = 0
    raw_response: Any = None

    @property
    def total_tokens(self) -> int:
        """Total tokens used (input + output)."""
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "tool_calls": self.tool_calls,
            "cached_tokens": self.cached_tokens,
        }

    def to_otel_attributes(self) -> dict[str, Any]:
        """Export as OpenTelemetry span attributes."""
        return {
            "llm.model": self.model,
            "llm.provider": self.provider,
            "llm.input_tokens": self.input_tokens,
            "llm.output_tokens": self.output_tokens,
            "llm.total_tokens": self.total_tokens,
            "llm.latency_ms": self.latency_ms,
            "llm.finish_reason": self.finish_reason or "",
            "llm.cached_tokens": self.cached_tokens,
        }


@dataclass(frozen=True, slots=True)
class STTResponse:
    """Standardized response from Speech-to-Text providers.

    Captures transcription, confidence, and audio metadata.

    Attributes:
        text: The transcribed text.
        confidence: Confidence score (0.0 to 1.0).
        duration_ms: Audio duration in milliseconds.
        language: Detected or specified language code.
        provider: Provider name (e.g., "deepgram", "whisper", "google").
        model: Model identifier if applicable.
        latency_ms: Processing latency in milliseconds.
        words: Word-level timestamps and confidence (if available).
        is_final: Whether this is a final or interim result.
        raw_response: Original provider response for debugging.
    """

    text: str
    confidence: float = 1.0
    duration_ms: float = 0.0
    language: str = "en"
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    words: list[dict[str, Any]] = field(default_factory=list)
    is_final: bool = True
    raw_response: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "text": self.text,
            "confidence": self.confidence,
            "duration_ms": self.duration_ms,
            "language": self.language,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "words": self.words,
            "is_final": self.is_final,
        }

    def to_otel_attributes(self) -> dict[str, Any]:
        """Export as OpenTelemetry span attributes."""
        return {
            "stt.provider": self.provider,
            "stt.model": self.model,
            "stt.confidence": self.confidence,
            "stt.duration_ms": self.duration_ms,
            "stt.language": self.language,
            "stt.latency_ms": self.latency_ms,
            "stt.is_final": self.is_final,
        }


@dataclass(frozen=True, slots=True)
class TTSResponse:
    """Standardized response from Text-to-Speech providers.

    Captures audio data and synthesis metadata.

    Attributes:
        audio: Raw audio bytes.
        duration_ms: Audio duration in milliseconds.
        sample_rate: Audio sample rate in Hz.
        format: Audio format (e.g., "pcm_16", "mp3", "opus").
        provider: Provider name (e.g., "elevenlabs", "google", "azure").
        model: Model/voice identifier.
        latency_ms: Processing latency in milliseconds.
        channels: Number of audio channels.
        characters_processed: Number of input characters processed.
        raw_response: Original provider response for debugging.
    """

    audio: bytes
    duration_ms: float = 0.0
    sample_rate: int = 16000
    format: str = "pcm_16"
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    channels: int = 1
    characters_processed: int = 0
    raw_response: Any = None

    @property
    def byte_count(self) -> int:
        """Number of audio bytes."""
        return len(self.audio)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization (excludes audio bytes)."""
        return {
            "byte_count": self.byte_count,
            "duration_ms": self.duration_ms,
            "sample_rate": self.sample_rate,
            "format": self.format,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "channels": self.channels,
            "characters_processed": self.characters_processed,
        }

    def to_otel_attributes(self) -> dict[str, Any]:
        """Export as OpenTelemetry span attributes."""
        return {
            "tts.provider": self.provider,
            "tts.model": self.model,
            "tts.duration_ms": self.duration_ms,
            "tts.sample_rate": self.sample_rate,
            "tts.format": self.format,
            "tts.latency_ms": self.latency_ms,
            "tts.byte_count": self.byte_count,
            "tts.characters_processed": self.characters_processed,
        }


__all__ = [
    "LLMResponse",
    "STTResponse",
    "TTSResponse",
]
