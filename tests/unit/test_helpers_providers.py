"""Tests for the provider response types helper module."""

from __future__ import annotations

import pytest

from stageflow.helpers.providers import (
    LLMResponse,
    STTResponse,
    TTSResponse,
)


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_basic_creation(self):
        """Should create LLMResponse with required fields."""
        response = LLMResponse(
            content="Hello, world!",
            model="gpt-4",
            provider="openai",
        )

        assert response.content == "Hello, world!"
        assert response.model == "gpt-4"
        assert response.provider == "openai"

    def test_token_usage(self):
        """Should track token usage."""
        response = LLMResponse(
            content="Test",
            model="gpt-4",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
        )

        assert response.input_tokens == 100
        assert response.output_tokens == 50
        assert response.total_tokens == 150

    def test_cached_tokens(self):
        """Should track cached tokens."""
        response = LLMResponse(
            content="Test",
            model="gpt-4",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            cached_tokens=30,
        )

        assert response.cached_tokens == 30

    def test_latency_tracking(self):
        """Should track latency."""
        response = LLMResponse(
            content="Test",
            model="gpt-4",
            provider="openai",
            latency_ms=150.5,
        )

        assert response.latency_ms == 150.5

    def test_tool_calls(self):
        """Should store tool calls."""
        tool_calls = [
            {"id": "call_1", "name": "calculator", "arguments": {"x": 1}},
            {"id": "call_2", "name": "weather", "arguments": {"city": "NYC"}},
        ]
        response = LLMResponse(
            content="",
            model="gpt-4",
            provider="openai",
            tool_calls=tool_calls,
        )

        assert len(response.tool_calls) == 2
        assert response.tool_calls[0]["name"] == "calculator"

    def test_finish_reason(self):
        """Should track finish reason."""
        response = LLMResponse(
            content="Test",
            model="gpt-4",
            provider="openai",
            finish_reason="stop",
        )

        assert response.finish_reason == "stop"

    def test_to_dict(self):
        """Should serialize to dictionary."""
        response = LLMResponse(
            content="Hello",
            model="gpt-4",
            provider="openai",
            input_tokens=10,
            output_tokens=5,
            latency_ms=100.0,
            finish_reason="stop",
        )

        result = response.to_dict()

        assert result["content"] == "Hello"
        assert result["model"] == "gpt-4"
        assert result["provider"] == "openai"
        assert result["input_tokens"] == 10
        assert result["output_tokens"] == 5
        assert result["total_tokens"] == 15
        assert result["latency_ms"] == 100.0
        assert result["finish_reason"] == "stop"

    def test_to_otel_attributes(self):
        """Should export OpenTelemetry attributes."""
        response = LLMResponse(
            content="Test",
            model="gpt-4",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            latency_ms=150.0,
            cached_tokens=20,
        )

        attrs = response.to_otel_attributes()

        assert attrs["llm.model"] == "gpt-4"
        assert attrs["llm.provider"] == "openai"
        assert attrs["llm.input_tokens"] == 100
        assert attrs["llm.output_tokens"] == 50
        assert attrs["llm.total_tokens"] == 150
        assert attrs["llm.latency_ms"] == 150.0
        assert attrs["llm.cached_tokens"] == 20

    def test_frozen(self):
        """Should be immutable."""
        response = LLMResponse(
            content="Test",
            model="gpt-4",
            provider="openai",
        )

        with pytest.raises(AttributeError):
            response.content = "Modified"  # type: ignore

    def test_raw_response_storage(self):
        """Should store raw response for debugging."""
        raw = {"id": "chatcmpl-123", "object": "chat.completion"}
        response = LLMResponse(
            content="Test",
            model="gpt-4",
            provider="openai",
            raw_response=raw,
        )

        assert response.raw_response == raw


class TestSTTResponse:
    """Tests for STTResponse dataclass."""

    def test_basic_creation(self):
        """Should create STTResponse with required fields."""
        response = STTResponse(text="Hello, world!")

        assert response.text == "Hello, world!"
        assert response.confidence == 1.0  # Default
        assert response.language == "en"  # Default

    def test_confidence_score(self):
        """Should track confidence score."""
        response = STTResponse(
            text="Hello",
            confidence=0.95,
        )

        assert response.confidence == 0.95

    def test_duration_tracking(self):
        """Should track audio duration."""
        response = STTResponse(
            text="Hello",
            duration_ms=1500.0,
        )

        assert response.duration_ms == 1500.0

    def test_language_detection(self):
        """Should track detected language."""
        response = STTResponse(
            text="Bonjour",
            language="fr",
        )

        assert response.language == "fr"

    def test_provider_info(self):
        """Should track provider information."""
        response = STTResponse(
            text="Hello",
            provider="deepgram",
            model="nova-2",
        )

        assert response.provider == "deepgram"
        assert response.model == "nova-2"

    def test_word_timestamps(self):
        """Should store word-level timestamps."""
        words = [
            {"word": "hello", "start": 0.0, "end": 0.5, "confidence": 0.98},
            {"word": "world", "start": 0.6, "end": 1.0, "confidence": 0.95},
        ]
        response = STTResponse(
            text="hello world",
            words=words,
        )

        assert len(response.words) == 2
        assert response.words[0]["word"] == "hello"

    def test_interim_vs_final(self):
        """Should track interim vs final results."""
        interim = STTResponse(text="hel", is_final=False)
        final = STTResponse(text="hello", is_final=True)

        assert not interim.is_final
        assert final.is_final

    def test_to_dict(self):
        """Should serialize to dictionary."""
        response = STTResponse(
            text="Hello",
            confidence=0.95,
            duration_ms=1000.0,
            language="en",
            provider="whisper",
            model="large-v3",
            latency_ms=200.0,
        )

        result = response.to_dict()

        assert result["text"] == "Hello"
        assert result["confidence"] == 0.95
        assert result["duration_ms"] == 1000.0
        assert result["language"] == "en"
        assert result["provider"] == "whisper"
        assert result["model"] == "large-v3"
        assert result["latency_ms"] == 200.0

    def test_to_otel_attributes(self):
        """Should export OpenTelemetry attributes."""
        response = STTResponse(
            text="Hello",
            confidence=0.95,
            duration_ms=1000.0,
            language="en",
            provider="deepgram",
            model="nova-2",
            latency_ms=150.0,
        )

        attrs = response.to_otel_attributes()

        assert attrs["stt.provider"] == "deepgram"
        assert attrs["stt.model"] == "nova-2"
        assert attrs["stt.confidence"] == 0.95
        assert attrs["stt.duration_ms"] == 1000.0
        assert attrs["stt.language"] == "en"
        assert attrs["stt.latency_ms"] == 150.0

    def test_frozen(self):
        """Should be immutable."""
        response = STTResponse(text="Hello")

        with pytest.raises(AttributeError):
            response.text = "Modified"  # type: ignore


class TestTTSResponse:
    """Tests for TTSResponse dataclass."""

    def test_basic_creation(self):
        """Should create TTSResponse with required fields."""
        audio = b"\x00\x01\x02\x03" * 100
        response = TTSResponse(audio=audio)

        assert response.audio == audio
        assert response.byte_count == 400

    def test_audio_metadata(self):
        """Should track audio metadata."""
        response = TTSResponse(
            audio=b"\x00" * 1000,
            duration_ms=500.0,
            sample_rate=24000,
            format="mp3",
            channels=2,
        )

        assert response.duration_ms == 500.0
        assert response.sample_rate == 24000
        assert response.format == "mp3"
        assert response.channels == 2

    def test_provider_info(self):
        """Should track provider information."""
        response = TTSResponse(
            audio=b"\x00" * 100,
            provider="elevenlabs",
            model="eleven_multilingual_v2",
        )

        assert response.provider == "elevenlabs"
        assert response.model == "eleven_multilingual_v2"

    def test_latency_tracking(self):
        """Should track processing latency."""
        response = TTSResponse(
            audio=b"\x00" * 100,
            latency_ms=250.0,
        )

        assert response.latency_ms == 250.0

    def test_characters_processed(self):
        """Should track input characters."""
        response = TTSResponse(
            audio=b"\x00" * 100,
            characters_processed=50,
        )

        assert response.characters_processed == 50

    def test_byte_count_property(self):
        """Should calculate byte count from audio."""
        response = TTSResponse(audio=b"\x00" * 12345)

        assert response.byte_count == 12345

    def test_to_dict_excludes_audio(self):
        """Should serialize without raw audio bytes."""
        response = TTSResponse(
            audio=b"\x00" * 1000,
            duration_ms=500.0,
            sample_rate=16000,
            format="pcm_16",
            provider="google",
            model="wavenet",
            latency_ms=100.0,
            characters_processed=25,
        )

        result = response.to_dict()

        assert "audio" not in result
        assert result["byte_count"] == 1000
        assert result["duration_ms"] == 500.0
        assert result["sample_rate"] == 16000
        assert result["format"] == "pcm_16"
        assert result["provider"] == "google"
        assert result["model"] == "wavenet"
        assert result["latency_ms"] == 100.0
        assert result["characters_processed"] == 25

    def test_to_otel_attributes(self):
        """Should export OpenTelemetry attributes."""
        response = TTSResponse(
            audio=b"\x00" * 1000,
            duration_ms=500.0,
            sample_rate=16000,
            format="pcm_16",
            provider="azure",
            model="neural",
            latency_ms=150.0,
            characters_processed=30,
        )

        attrs = response.to_otel_attributes()

        assert attrs["tts.provider"] == "azure"
        assert attrs["tts.model"] == "neural"
        assert attrs["tts.duration_ms"] == 500.0
        assert attrs["tts.sample_rate"] == 16000
        assert attrs["tts.format"] == "pcm_16"
        assert attrs["tts.latency_ms"] == 150.0
        assert attrs["tts.byte_count"] == 1000
        assert attrs["tts.characters_processed"] == 30

    def test_frozen(self):
        """Should be immutable."""
        response = TTSResponse(audio=b"\x00" * 100)

        with pytest.raises(AttributeError):
            response.audio = b"\x01" * 100  # type: ignore


class TestProviderResponseImports:
    """Tests for provider response imports from helpers package."""

    def test_import_from_helpers(self):
        """Should be importable from stageflow.helpers."""
        from stageflow.helpers import LLMResponse, STTResponse, TTSResponse

        # Verify they're the same classes
        assert LLMResponse is not None
        assert STTResponse is not None
        assert TTSResponse is not None
