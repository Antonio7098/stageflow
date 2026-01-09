"""StagePorts - Injected capabilities for stages (callbacks, services, db).

This module defines typed ports for different domains, following the
Interface Segregation Principle. Stages only receive the ports they need.
"""

from __future__ import annotations

from asyncio import Lock
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CorePorts:
    """Core capabilities needed by most stages.

    These are the fundamental capabilities that most stages need:
    - Database access
    - Status updates
    - Basic logging
    """

    # Database and persistence
    db: Any = None
    db_lock: Lock | None = None
    call_logger_db: Any = None

    # Core callbacks
    send_status: Callable[[str, str, dict[str, Any] | None], Awaitable[None]] | None = None
    call_logger: Any = None
    retry_fn: Any = None


@dataclass(frozen=True, slots=True)
class LLMPorts:
    """Ports for LLM-powered stages.

    Provides access to language models and related services.
    """

    llm_provider: Any = None
    chat_service: Any = None
    llm_chunk_queue: Any = None
    send_token: Callable[[str], Awaitable[None]] | None = None


@dataclass(frozen=True, slots=True)
class AudioPorts:
    """Ports for audio processing stages.

    Provides access to audio providers and streaming capabilities.
    """

    tts_provider: Any = None
    stt_provider: Any = None
    send_audio_chunk: Callable[[bytes, str, int, bool], Awaitable[None]] | None = None
    send_transcript: Callable[[Any, str, float, int], Awaitable[None]] | None = None
    audio_data: bytes | None = None
    audio_format: str | None = None
    tts_text_queue: Any = None
    recording: Any = None




# Core ports factory
def create_core_ports(
    *,
    db: Any = None,
    db_lock: Lock | None = None,
    call_logger_db: Any = None,
    send_status: Callable[[str, str, dict[str, Any] | None], Awaitable[None]] | None = None,
    call_logger: Any = None,
    retry_fn: Any = None,
) -> CorePorts:
    """Create CorePorts with essential capabilities.
    
    Args:
        db: Database session for persistence operations
        db_lock: Optional lock for preventing concurrent DB access
        call_logger_db: Database session for provider call logging
        send_status: Callback for status updates
        call_logger: Logger for tracking provider API calls
        retry_fn: Retry function for failed operations
        
    Returns:
        CorePorts instance
    """
    return CorePorts(
        db=db,
        db_lock=db_lock,
        call_logger_db=call_logger_db,
        send_status=send_status,
        call_logger=call_logger,
        retry_fn=retry_fn,
    )


# LLM ports factory
def create_llm_ports(
    *,
    llm_provider: Any = None,
    chat_service: Any = None,
    llm_chunk_queue: Any = None,
    send_token: Callable[[str], Awaitable[None]] | None = None,
) -> LLMPorts:
    """Create LLMPorts for language model operations.
    
    Args:
        llm_provider: LLM provider for text generation
        chat_service: Chat service for building context and running LLM
        llm_chunk_queue: Queue for LLM chunks in streaming pipeline
        send_token: Callback for streaming tokens
        
    Returns:
        LLMPorts instance
    """
    return LLMPorts(
        llm_provider=llm_provider,
        chat_service=chat_service,
        llm_chunk_queue=llm_chunk_queue,
        send_token=send_token,
    )


# Audio ports factory
def create_audio_ports(
    *,
    tts_provider: Any = None,
    stt_provider: Any = None,
    send_audio_chunk: Callable[[bytes, str, int, bool], Awaitable[None]] | None = None,
    send_transcript: Callable[[Any, str, float, int], Awaitable[None]] | None = None,
    audio_data: bytes | None = None,
    audio_format: str | None = None,
    tts_text_queue: Any = None,
    recording: Any = None,
) -> AudioPorts:
    """Create AudioPorts for audio processing operations.
    
    Args:
        tts_provider: TTS provider for text-to-speech synthesis
        stt_provider: STT provider for speech-to-text transcription
        send_audio_chunk: Callback for streaming audio chunks
        send_transcript: Callback for sending STT transcript
        audio_data: Raw audio bytes
        audio_format: Audio format string
        tts_text_queue: Queue for text chunks to be synthesized by TTS
        recording: Recording metadata
        
    Returns:
        AudioPorts instance
    """
    return AudioPorts(
        tts_provider=tts_provider,
        stt_provider=stt_provider,
        send_audio_chunk=send_audio_chunk,
        send_transcript=send_transcript,
        audio_data=audio_data,
        audio_format=audio_format,
        tts_text_queue=tts_text_queue,
        recording=recording,
    )




__all__ = [
    "CorePorts",
    "LLMPorts",
    "AudioPorts",
    "create_core_ports",
    "create_llm_ports",
    "create_audio_ports",
]
