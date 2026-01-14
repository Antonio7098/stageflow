"""Mock providers for testing pipelines without real API keys.

This module provides deterministic mock implementations of common providers:
- LLM providers (chat completion)
- STT providers (speech-to-text)
- TTS providers (text-to-speech)
- Auth providers (JWT validation)
- Tool executors (function calling)

Usage:
    from stageflow.helpers import MockLLMProvider, MockSTTProvider

    # Create mock LLM with canned responses
    llm = MockLLMProvider(
        responses=["Hello!", "How can I help?"],
        latency_ms=50,
    )

    # Use in stages
    response = await llm.complete("What is 2+2?")
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4


@dataclass
class MockMessage:
    """A mock chat message."""

    role: str
    content: str
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


@dataclass
class MockCompletion:
    """A mock LLM completion response."""

    id: str
    content: str
    role: str = "assistant"
    model: str = "mock-model"
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30,
    })
    tool_calls: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to OpenAI-style response dict."""
        return {
            "id": self.id,
            "object": "chat.completion",
            "created": int(datetime.now(UTC).timestamp()),
            "model": self.model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": self.role,
                    "content": self.content,
                    "tool_calls": self.tool_calls,
                },
                "finish_reason": self.finish_reason,
            }],
            "usage": self.usage,
        }


class MockLLMProvider:
    """Mock LLM provider for testing chat pipelines.

    Provides deterministic responses with configurable latency and behavior.
    Supports streaming, tool calls, and error simulation.

    Example:
        # Simple responses
        llm = MockLLMProvider(responses=["Hello!", "Goodbye!"])
        response = await llm.complete("Hi")  # Returns "Hello!"
        response = await llm.complete("Bye")  # Returns "Goodbye!"

        # Pattern-based responses
        llm = MockLLMProvider(patterns={
            r"weather": "The weather is sunny.",
            r"time": "It is noon.",
        })

        # Echo mode
        llm = MockLLMProvider(echo=True)
        response = await llm.complete("Hello")  # Returns "Echo: Hello"
    """

    def __init__(
        self,
        *,
        responses: list[str] | None = None,
        patterns: dict[str, str] | None = None,
        echo: bool = False,
        latency_ms: float = 0,
        latency_jitter_ms: float = 0,
        fail_rate: float = 0.0,
        fail_error: str = "Mock LLM error",
        tool_responses: dict[str, Any] | None = None,
        token_counter: Callable[[str], int] | None = None,
    ) -> None:
        """Initialize mock LLM.

        Args:
            responses: List of canned responses (cycles through them).
            patterns: Regex patterns mapped to responses.
            echo: If True, echo back the input.
            latency_ms: Simulated latency in milliseconds.
            latency_jitter_ms: Random jitter added to latency.
            fail_rate: Probability of simulated failure (0-1).
            fail_error: Error message for failures.
            tool_responses: Tool name to response mapping.
            token_counter: Custom token counting function.
        """
        self._responses = responses or ["Mock response"]
        self._patterns = patterns or {}
        self._echo = echo
        self._latency_ms = latency_ms
        self._latency_jitter_ms = latency_jitter_ms
        self._fail_rate = fail_rate
        self._fail_error = fail_error
        self._tool_responses = tool_responses or {}
        self._token_counter = token_counter or (lambda s: len(s) // 4)
        self._response_index = 0
        self._call_count = 0
        self._call_history: list[dict[str, Any]] = []

    async def _simulate_latency(self) -> None:
        """Simulate network latency."""
        if self._latency_ms > 0:
            jitter = random.uniform(-self._latency_jitter_ms, self._latency_jitter_ms)
            delay = max(0, self._latency_ms + jitter) / 1000
            await asyncio.sleep(delay)

    def _should_fail(self) -> bool:
        """Check if this call should fail."""
        return random.random() < self._fail_rate

    def _get_response(self, prompt: str) -> str:
        """Get response for a prompt."""
        # Check patterns first
        for pattern, response in self._patterns.items():
            if re.search(pattern, prompt, re.IGNORECASE):
                return response

        # Echo mode
        if self._echo:
            return f"Echo: {prompt}"

        # Cycle through responses
        response = self._responses[self._response_index % len(self._responses)]
        self._response_index += 1
        return response

    async def complete(
        self,
        prompt: str,
        *,
        messages: list[MockMessage] | None = None,
        model: str = "mock-model",
        **kwargs: Any,
    ) -> MockCompletion:
        """Generate a completion.

        Args:
            prompt: The prompt text (or last message content).
            messages: Full message history.
            model: Model name (ignored, for compatibility).
            **kwargs: Additional args (ignored).

        Returns:
            MockCompletion response.

        Raises:
            Exception: If simulated failure occurs.
        """
        self._call_count += 1
        self._call_history.append({
            "prompt": prompt,
            "messages": messages,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        await self._simulate_latency()

        if self._should_fail():
            raise Exception(self._fail_error)

        content = self._get_response(prompt)
        prompt_tokens = self._token_counter(prompt)
        completion_tokens = self._token_counter(content)

        return MockCompletion(
            id=f"mock-{uuid4().hex[:8]}",
            content=content,
            model=model,
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        )

    async def stream(
        self,
        prompt: str,
        *,
        chunk_size: int = 5,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a completion in chunks.

        Args:
            prompt: The prompt text.
            chunk_size: Characters per chunk.
            **kwargs: Additional args.

        Yields:
            Content chunks.
        """
        await self._simulate_latency()

        if self._should_fail():
            raise Exception(self._fail_error)

        content = self._get_response(prompt)

        # Yield in chunks
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            yield chunk
            await asyncio.sleep(0.01)  # Small delay between chunks

    @property
    def call_count(self) -> int:
        """Get number of calls made."""
        return self._call_count

    @property
    def call_history(self) -> list[dict[str, Any]]:
        """Get call history."""
        return self._call_history

    def reset(self) -> None:
        """Reset call count and history."""
        self._call_count = 0
        self._call_history.clear()
        self._response_index = 0


@dataclass
class MockTranscription:
    """A mock STT transcription result."""

    text: str
    confidence: float = 0.95
    duration_ms: float = 0.0
    language: str = "en"
    words: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "text": self.text,
            "confidence": self.confidence,
            "duration_ms": self.duration_ms,
            "language": self.language,
            "words": self.words,
        }


class MockSTTProvider:
    """Mock Speech-to-Text provider for testing voice pipelines.

    Provides deterministic transcriptions based on audio hash or patterns.

    Example:
        stt = MockSTTProvider(
            transcriptions=["Hello world", "How are you?"],
            latency_ms=100,
        )

        result = await stt.transcribe(audio_bytes)
    """

    def __init__(
        self,
        *,
        transcriptions: list[str] | None = None,
        audio_map: dict[str, str] | None = None,
        latency_ms: float = 100,
        latency_jitter_ms: float = 20,
        fail_rate: float = 0.0,
        simulate_confidence: bool = True,
    ) -> None:
        """Initialize mock STT.

        Args:
            transcriptions: List of transcriptions (cycles through).
            audio_map: Hash-to-transcription mapping for deterministic results.
            latency_ms: Simulated latency.
            latency_jitter_ms: Random jitter.
            fail_rate: Probability of failure.
            simulate_confidence: Add realistic confidence values.
        """
        self._transcriptions = transcriptions or ["Mock transcription"]
        self._audio_map = audio_map or {}
        self._latency_ms = latency_ms
        self._latency_jitter_ms = latency_jitter_ms
        self._fail_rate = fail_rate
        self._simulate_confidence = simulate_confidence
        self._transcription_index = 0
        self._call_count = 0

    async def _simulate_latency(self) -> None:
        """Simulate processing latency."""
        if self._latency_ms > 0:
            jitter = random.uniform(-self._latency_jitter_ms, self._latency_jitter_ms)
            delay = max(0, self._latency_ms + jitter) / 1000
            await asyncio.sleep(delay)

    def _hash_audio(self, audio: bytes) -> str:
        """Get deterministic hash of audio."""
        return hashlib.md5(audio).hexdigest()[:16]

    async def transcribe(
        self,
        audio: bytes,
        *,
        language: str = "en",
        **kwargs: Any,
    ) -> MockTranscription:
        """Transcribe audio to text.

        Args:
            audio: Audio bytes.
            language: Target language.
            **kwargs: Additional args.

        Returns:
            MockTranscription result.
        """
        self._call_count += 1
        await self._simulate_latency()

        if random.random() < self._fail_rate:
            raise Exception("Mock STT error")

        # Check audio map first
        audio_hash = self._hash_audio(audio)
        if audio_hash in self._audio_map:
            text = self._audio_map[audio_hash]
        else:
            # Cycle through transcriptions
            text = self._transcriptions[self._transcription_index % len(self._transcriptions)]
            self._transcription_index += 1

        # Simulate confidence
        confidence = 0.95 if not self._simulate_confidence else random.uniform(0.85, 0.99)

        # Estimate duration from audio size (16kHz, 16-bit mono)
        duration_ms = (len(audio) / (16000 * 2)) * 1000

        return MockTranscription(
            text=text,
            confidence=confidence,
            duration_ms=duration_ms,
            language=language,
        )

    @property
    def call_count(self) -> int:
        """Get call count."""
        return self._call_count

    def reset(self) -> None:
        """Reset state."""
        self._call_count = 0
        self._transcription_index = 0


@dataclass
class MockAudioChunk:
    """A mock TTS audio chunk."""

    data: bytes
    sample_rate: int = 16000
    channels: int = 1
    format: str = "pcm_16"


class MockTTSProvider:
    """Mock Text-to-Speech provider for testing voice pipelines.

    Generates deterministic audio data from text input.

    Example:
        tts = MockTTSProvider(latency_ms=50)

        audio = await tts.synthesize("Hello world")

        # Streaming
        async for chunk in tts.stream("Hello world"):
            play(chunk)
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        latency_ms: float = 50,
        bytes_per_char: int = 100,
        fail_rate: float = 0.0,
    ) -> None:
        """Initialize mock TTS.

        Args:
            sample_rate: Output sample rate.
            latency_ms: Simulated latency.
            bytes_per_char: Audio bytes per character (for sizing).
            fail_rate: Probability of failure.
        """
        self._sample_rate = sample_rate
        self._latency_ms = latency_ms
        self._bytes_per_char = bytes_per_char
        self._fail_rate = fail_rate
        self._call_count = 0

    async def _simulate_latency(self) -> None:
        """Simulate processing latency."""
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000)

    def _generate_audio(self, text: str) -> bytes:
        """Generate deterministic audio bytes from text."""
        # Generate pseudo-random but deterministic audio
        seed = hashlib.md5(text.encode()).digest()
        size = len(text) * self._bytes_per_char
        # Create audio that's deterministic but looks like PCM data
        audio = bytes((seed[i % len(seed)] ^ (i % 256)) for i in range(size))
        return audio

    async def synthesize(
        self,
        text: str,
        *,
        voice: str = "default",
        **kwargs: Any,
    ) -> bytes:
        """Synthesize text to audio.

        Args:
            text: Text to synthesize.
            voice: Voice name (ignored).
            **kwargs: Additional args.

        Returns:
            Audio bytes.
        """
        self._call_count += 1
        await self._simulate_latency()

        if random.random() < self._fail_rate:
            raise Exception("Mock TTS error")

        return self._generate_audio(text)

    async def stream(
        self,
        text: str,
        *,
        chunk_duration_ms: int = 100,
        **kwargs: Any,
    ) -> AsyncIterator[MockAudioChunk]:
        """Stream synthesized audio in chunks.

        Args:
            text: Text to synthesize.
            chunk_duration_ms: Duration of each chunk.
            **kwargs: Additional args.

        Yields:
            MockAudioChunk objects.
        """
        await self._simulate_latency()

        if random.random() < self._fail_rate:
            raise Exception("Mock TTS error")

        full_audio = self._generate_audio(text)

        # Calculate chunk size
        bytes_per_ms = (self._sample_rate * 2) / 1000  # 16-bit audio
        chunk_bytes = int(bytes_per_ms * chunk_duration_ms)

        # Yield chunks
        for i in range(0, len(full_audio), chunk_bytes):
            chunk_data = full_audio[i:i + chunk_bytes]
            yield MockAudioChunk(
                data=chunk_data,
                sample_rate=self._sample_rate,
            )
            await asyncio.sleep(chunk_duration_ms / 1000)

    @property
    def call_count(self) -> int:
        """Get call count."""
        return self._call_count

    def reset(self) -> None:
        """Reset state."""
        self._call_count = 0


@dataclass
class MockJWTClaims:
    """Mock JWT claims."""

    sub: str
    aud: str = "stageflow"
    iss: str = "mock-auth"
    exp: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(hours=1))
    iat: datetime = field(default_factory=lambda: datetime.now(UTC))
    roles: list[str] = field(default_factory=list)
    org_id: str | None = None
    custom: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "sub": self.sub,
            "aud": self.aud,
            "iss": self.iss,
            "exp": int(self.exp.timestamp()),
            "iat": int(self.iat.timestamp()),
            "roles": self.roles,
            "org_id": self.org_id,
            **self.custom,
        }


class MockAuthProvider:
    """Mock authentication provider for testing auth flows.

    Validates mock tokens and returns configurable claims.

    Example:
        auth = MockAuthProvider(
            valid_tokens={"test-token": MockJWTClaims(sub="user-123")},
        )

        claims = await auth.validate("test-token")
        print(claims.sub)  # "user-123"
    """

    def __init__(
        self,
        *,
        valid_tokens: dict[str, MockJWTClaims] | None = None,
        default_claims: MockJWTClaims | None = None,
        accept_any: bool = False,
        fail_rate: float = 0.0,
    ) -> None:
        """Initialize mock auth.

        Args:
            valid_tokens: Token-to-claims mapping.
            default_claims: Default claims for unknown tokens (if accept_any).
            accept_any: Accept any token with default claims.
            fail_rate: Probability of auth failure.
        """
        self._valid_tokens = valid_tokens or {}
        self._default_claims = default_claims or MockJWTClaims(sub="mock-user")
        self._accept_any = accept_any
        self._fail_rate = fail_rate
        self._validation_count = 0
        self._validation_history: list[dict[str, Any]] = []

    async def validate(
        self,
        token: str,
        *,
        audience: str | None = None,
    ) -> MockJWTClaims:
        """Validate a token and return claims.

        Args:
            token: The token to validate.
            audience: Expected audience (optional).

        Returns:
            MockJWTClaims if valid.

        Raises:
            ValueError: If token is invalid.
        """
        self._validation_count += 1
        self._validation_history.append({
            "token": token[:20] + "..." if len(token) > 20 else token,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        if random.random() < self._fail_rate:
            raise ValueError("Mock auth failure")

        # Check valid tokens
        if token in self._valid_tokens:
            claims = self._valid_tokens[token]
            # Check expiry
            if claims.exp < datetime.now(UTC):
                raise ValueError("Token expired")
            return claims

        # Accept any mode
        if self._accept_any:
            return self._default_claims

        raise ValueError("Invalid token")

    def create_token(
        self,
        sub: str,
        *,
        roles: list[str] | None = None,
        org_id: str | None = None,
        expires_in_hours: int = 1,
    ) -> tuple[str, MockJWTClaims]:
        """Create a mock token (for testing).

        Args:
            sub: Subject (user ID).
            roles: User roles.
            org_id: Organization ID.
            expires_in_hours: Token lifetime.

        Returns:
            Tuple of (token_string, claims).
        """
        claims = MockJWTClaims(
            sub=sub,
            roles=roles or [],
            org_id=org_id,
            exp=datetime.now(UTC) + timedelta(hours=expires_in_hours),
        )
        token = f"mock-{uuid4().hex}"
        self._valid_tokens[token] = claims
        return token, claims

    @property
    def validation_count(self) -> int:
        """Get validation count."""
        return self._validation_count

    def reset(self) -> None:
        """Reset state."""
        self._validation_count = 0
        self._validation_history.clear()


@dataclass
class MockToolResult:
    """Result of a mock tool execution."""

    success: bool
    output: Any
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class MockToolExecutor:
    """Mock tool executor for testing agent pipelines.

    Executes mock tools with configurable behavior.

    Example:
        executor = MockToolExecutor(
            tools={
                "calculator": lambda args: {"result": eval(args["expression"])},
                "weather": lambda args: {"temp": 72, "condition": "sunny"},
            }
        )

        result = await executor.execute("calculator", {"expression": "2+2"})
        print(result.output)  # {"result": 4}
    """

    def __init__(
        self,
        *,
        tools: dict[str, Callable[[dict[str, Any]], Any]] | None = None,
        default_output: Any = None,
        latency_ms: float = 10,
        fail_rate: float = 0.0,
    ) -> None:
        """Initialize mock executor.

        Args:
            tools: Tool name to implementation mapping.
            default_output: Default output for unknown tools.
            latency_ms: Simulated latency.
            fail_rate: Probability of failure.
        """
        if default_output is None:
            default_output = {"status": "ok"}
        self._tools = tools or {}
        self._default_output = default_output
        self._latency_ms = latency_ms
        self._fail_rate = fail_rate
        self._execution_count = 0
        self._execution_history: list[dict[str, Any]] = []

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MockToolResult:
        """Execute a tool.

        Args:
            tool_name: Name of the tool.
            arguments: Tool arguments.

        Returns:
            MockToolResult with output.
        """
        start = datetime.now(UTC)
        self._execution_count += 1
        self._execution_history.append({
            "tool": tool_name,
            "arguments": arguments,
            "timestamp": start.isoformat(),
        })

        # Simulate latency
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000)

        # Check failure
        if random.random() < self._fail_rate:
            return MockToolResult(
                success=False,
                output=None,
                error="Mock tool execution failed",
                duration_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
            )

        # Execute tool
        try:
            if tool_name in self._tools:
                output = self._tools[tool_name](arguments)
            else:
                output = self._default_output

            return MockToolResult(
                success=True,
                output=output,
                duration_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
            )
        except Exception as e:
            return MockToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
            )

    def register_tool(
        self,
        name: str,
        handler: Callable[[dict[str, Any]], Any],
    ) -> None:
        """Register a tool handler.

        Args:
            name: Tool name.
            handler: Tool implementation.
        """
        self._tools[name] = handler

    @property
    def execution_count(self) -> int:
        """Get execution count."""
        return self._execution_count

    @property
    def execution_history(self) -> list[dict[str, Any]]:
        """Get execution history."""
        return self._execution_history

    def reset(self) -> None:
        """Reset state."""
        self._execution_count = 0
        self._execution_history.clear()


__all__ = [
    "MockAudioChunk",
    "MockAuthProvider",
    "MockCompletion",
    "MockJWTClaims",
    "MockLLMProvider",
    "MockMessage",
    "MockSTTProvider",
    "MockTTSProvider",
    "MockToolExecutor",
    "MockToolResult",
    "MockTranscription",
]
