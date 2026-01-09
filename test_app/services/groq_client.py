"""Groq LLM client for real LLM integration."""

import os
from typing import AsyncIterator

try:
    from groq import AsyncGroq
except ImportError:
    AsyncGroq = None


class GroqClient:
    """Async Groq client wrapper."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self._client: AsyncGroq | None = None

    @property
    def client(self) -> "AsyncGroq":
        if self._client is None:
            if AsyncGroq is None:
                raise ImportError("groq package not installed. Run: pip install groq")
            if not self.api_key:
                raise ValueError("GROQ_API_KEY not set")
            self._client = AsyncGroq(api_key=self.api_key)
        return self._client

    async def chat(
        self,
        messages: list[dict],
        model: str = "llama-3.1-8b-instant",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Send a chat completion request and return the response."""
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def chat_stream(
        self,
        messages: list[dict],
        model: str = "llama-3.1-8b-instant",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Stream a chat completion response."""
        stream = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
