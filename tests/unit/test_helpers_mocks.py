"""Tests for the mock providers helper module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from stageflow.helpers.mocks import (
    MockAuthProvider,
    MockJWTClaims,
    MockLLMProvider,
    MockSTTProvider,
    MockToolExecutor,
    MockTTSProvider,
)


class TestMockLLMProvider:
    """Tests for MockLLMProvider."""

    @pytest.mark.asyncio
    async def test_returns_responses(self):
        """Should return configured responses."""
        llm = MockLLMProvider(responses=["Hello!", "Goodbye!"])

        result1 = await llm.complete("Hi")
        result2 = await llm.complete("Bye")

        assert result1.content == "Hello!"
        assert result2.content == "Goodbye!"

    @pytest.mark.asyncio
    async def test_cycles_through_responses(self):
        """Should cycle through responses."""
        llm = MockLLMProvider(responses=["A", "B"])

        assert (await llm.complete("")).content == "A"
        assert (await llm.complete("")).content == "B"
        assert (await llm.complete("")).content == "A"  # Cycles

    @pytest.mark.asyncio
    async def test_pattern_matching(self):
        """Should match patterns to responses."""
        llm = MockLLMProvider(
            patterns={
                r"weather": "It's sunny!",
                r"time": "It's noon.",
            }
        )

        assert (await llm.complete("What's the weather?")).content == "It's sunny!"
        assert (await llm.complete("What time is it?")).content == "It's noon."

    @pytest.mark.asyncio
    async def test_echo_mode(self):
        """Should echo input in echo mode."""
        llm = MockLLMProvider(echo=True)

        result = await llm.complete("Hello world")

        assert "Hello world" in result.content

    @pytest.mark.asyncio
    async def test_simulates_latency(self):
        """Should simulate configurable latency."""
        llm = MockLLMProvider(latency_ms=100)

        start = datetime.now(UTC)
        await llm.complete("test")
        elapsed = (datetime.now(UTC) - start).total_seconds() * 1000

        assert elapsed >= 90  # Some tolerance

    @pytest.mark.asyncio
    async def test_streaming(self):
        """Should stream response in chunks."""
        llm = MockLLMProvider(responses=["Hello world"], latency_ms=0)

        chunks = []
        async for chunk in llm.stream("test", chunk_size=5):
            chunks.append(chunk)

        assert "".join(chunks) == "Hello world"

    @pytest.mark.asyncio
    async def test_tracks_call_history(self):
        """Should track call history."""
        llm = MockLLMProvider()

        await llm.complete("First")
        await llm.complete("Second")

        assert llm.call_count == 2
        assert llm.call_history[0]["prompt"] == "First"
        assert llm.call_history[1]["prompt"] == "Second"

    @pytest.mark.asyncio
    async def test_reset(self):
        """Should reset state."""
        llm = MockLLMProvider(responses=["A", "B"])

        await llm.complete("")
        llm.reset()

        assert llm.call_count == 0
        assert (await llm.complete("")).content == "A"  # Back to first


class TestMockSTTProvider:
    """Tests for MockSTTProvider."""

    @pytest.mark.asyncio
    async def test_returns_transcriptions(self):
        """Should return configured transcriptions."""
        stt = MockSTTProvider(transcriptions=["Hello", "World"])

        result1 = await stt.transcribe(b"audio1")
        result2 = await stt.transcribe(b"audio2")

        assert result1.text == "Hello"
        assert result2.text == "World"

    @pytest.mark.asyncio
    async def test_deterministic_with_audio_map(self):
        """Should return deterministic results for mapped audio."""
        stt = MockSTTProvider()

        # Same audio should produce same transcription
        result1 = await stt.transcribe(b"same audio data")
        stt.reset()
        result2 = await stt.transcribe(b"same audio data")

        # Different audio should cycle
        await stt.transcribe(b"different audio")

        assert result1.text == result2.text

    @pytest.mark.asyncio
    async def test_includes_confidence(self):
        """Should include confidence score."""
        stt = MockSTTProvider(simulate_confidence=True)

        result = await stt.transcribe(b"audio")

        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_calculates_duration(self):
        """Should estimate duration from audio size."""
        stt = MockSTTProvider()

        # 32000 bytes at 16kHz 16-bit = 1000ms
        result = await stt.transcribe(b"\x00" * 32000)

        assert abs(result.duration_ms - 1000) < 100


class TestMockTTSProvider:
    """Tests for MockTTSProvider."""

    @pytest.mark.asyncio
    async def test_synthesizes_audio(self):
        """Should generate audio from text."""
        tts = MockTTSProvider()

        result = await tts.synthesize("Hello world")

        assert isinstance(result, bytes)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_deterministic_output(self):
        """Same text should produce same audio."""
        tts = MockTTSProvider()

        result1 = await tts.synthesize("Hello")
        result2 = await tts.synthesize("Hello")

        assert result1 == result2

    @pytest.mark.asyncio
    async def test_different_text_different_output(self):
        """Different text should produce different audio."""
        tts = MockTTSProvider()

        result1 = await tts.synthesize("Hello")
        result2 = await tts.synthesize("Goodbye")

        assert result1 != result2

    @pytest.mark.asyncio
    async def test_streaming(self):
        """Should stream audio in chunks."""
        tts = MockTTSProvider()

        chunks = []
        async for chunk in tts.stream("Hello world", chunk_duration_ms=50):
            chunks.append(chunk)

        assert len(chunks) > 0
        total_bytes = sum(len(c.data) for c in chunks)
        assert total_bytes > 0


class TestMockAuthProvider:
    """Tests for MockAuthProvider."""

    @pytest.mark.asyncio
    async def test_validates_known_tokens(self):
        """Should validate pre-configured tokens."""
        claims = MockJWTClaims(sub="user-123", roles=["admin"])
        auth = MockAuthProvider(valid_tokens={"valid-token": claims})

        result = await auth.validate("valid-token")

        assert result.sub == "user-123"
        assert "admin" in result.roles

    @pytest.mark.asyncio
    async def test_rejects_unknown_tokens(self):
        """Should reject unknown tokens."""
        auth = MockAuthProvider(valid_tokens={})

        with pytest.raises(ValueError, match="Invalid token"):
            await auth.validate("unknown-token")

    @pytest.mark.asyncio
    async def test_accept_any_mode(self):
        """Should accept any token in accept_any mode."""
        default_claims = MockJWTClaims(sub="default-user")
        auth = MockAuthProvider(accept_any=True, default_claims=default_claims)

        result = await auth.validate("any-random-token")

        assert result.sub == "default-user"

    @pytest.mark.asyncio
    async def test_creates_tokens(self):
        """Should create tokens for testing."""
        auth = MockAuthProvider()

        token, claims = auth.create_token(
            sub="test-user",
            roles=["editor"],
            org_id="org-123",
        )

        # Should be able to validate the created token
        result = await auth.validate(token)

        assert result.sub == "test-user"
        assert "editor" in result.roles
        assert result.org_id == "org-123"

    @pytest.mark.asyncio
    async def test_checks_expiry(self):
        """Should reject expired tokens."""
        expired_claims = MockJWTClaims(
            sub="user",
            exp=datetime.now(UTC) - timedelta(hours=1),  # Expired
        )
        auth = MockAuthProvider(valid_tokens={"expired": expired_claims})

        with pytest.raises(ValueError, match="expired"):
            await auth.validate("expired")

    @pytest.mark.asyncio
    async def test_tracks_validation_count(self):
        """Should track validation attempts."""
        auth = MockAuthProvider(accept_any=True)

        await auth.validate("token1")
        await auth.validate("token2")

        assert auth.validation_count == 2


class TestMockToolExecutor:
    """Tests for MockToolExecutor."""

    @pytest.mark.asyncio
    async def test_executes_registered_tools(self):
        """Should execute registered tools."""
        executor = MockToolExecutor(
            tools={
                "add": lambda args: {"result": args["a"] + args["b"]},
            }
        )

        result = await executor.execute("add", {"a": 2, "b": 3})

        assert result.success
        assert result.output["result"] == 5

    @pytest.mark.asyncio
    async def test_returns_default_for_unknown(self):
        """Should return default for unknown tools."""
        executor = MockToolExecutor(default_output={"status": "unknown"})

        result = await executor.execute("nonexistent", {})

        assert result.success
        assert result.output["status"] == "unknown"

    @pytest.mark.asyncio
    async def test_handles_tool_errors(self):
        """Should handle tool execution errors."""

        def failing_tool(_args):
            raise ValueError("Tool failed!")

        executor = MockToolExecutor(tools={"failing": failing_tool})

        result = await executor.execute("failing", {})

        assert not result.success
        assert "Tool failed!" in result.error

    @pytest.mark.asyncio
    async def test_tracks_execution_history(self):
        """Should track execution history."""
        executor = MockToolExecutor(
            tools={
                "tool1": lambda _args: {"ok": True},
                "tool2": lambda _args: {"ok": True},
            }
        )

        await executor.execute("tool1", {"x": 1})
        await executor.execute("tool2", {"y": 2})

        assert executor.execution_count == 2
        assert executor.execution_history[0]["tool"] == "tool1"
        assert executor.execution_history[1]["tool"] == "tool2"

    @pytest.mark.asyncio
    async def test_register_tool(self):
        """Should allow registering tools after creation."""
        executor = MockToolExecutor()

        executor.register_tool("dynamic", lambda _args: {"dynamic": True})

        result = await executor.execute("dynamic", {})

        assert result.success
        assert result.output["dynamic"] is True

    @pytest.mark.asyncio
    async def test_measures_duration(self):
        """Should measure execution duration."""
        executor = MockToolExecutor(
            tools={"slow": lambda _args: "done"},
            latency_ms=50,
        )

        result = await executor.execute("slow", {})

        assert result.duration_ms >= 40  # Some tolerance
