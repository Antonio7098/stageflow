"""Mock services for testing."""

import asyncio
import random
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass
class MockProfile:
    user_id: UUID
    display_name: str
    preferences: dict[str, Any]
    goals: list[str]


@dataclass
class MockMemory:
    recent_topics: list[str]
    key_facts: list[str]
    interaction_count: int


class MockProfileService:
    """Mock profile service that returns fake user profiles."""

    async def get_profile(self, user_id: UUID) -> MockProfile:
        await asyncio.sleep(random.uniform(0.1, 0.3))
        return MockProfile(
            user_id=user_id,
            display_name="Test User",
            preferences={
                "language": "en",
                "tone": "friendly",
                "verbosity": "concise",
            },
            goals=["Learn Python", "Build projects", "Understand AI"],
        )


class MockMemoryService:
    """Mock memory service that returns fake conversation context."""

    async def get_memory(self, _session_id: UUID) -> MockMemory:
        await asyncio.sleep(random.uniform(0.1, 0.3))
        return MockMemory(
            recent_topics=["stageflow", "pipelines", "DAG execution"],
            key_facts=[
                "User is building a pipeline framework",
                "Interested in observability",
                "Prefers visual debugging",
            ],
            interaction_count=random.randint(5, 50),
        )


class MockGuardService:
    """Mock guardrail service for content validation."""

    BLOCKED_WORDS = {"spam", "malicious", "inject"}

    async def check_input(self, text: str) -> tuple[bool, str | None]:
        """Check if input is safe. Returns (is_safe, reason)."""
        await asyncio.sleep(random.uniform(0.05, 0.1))
        text_lower = text.lower()
        for word in self.BLOCKED_WORDS:
            if word in text_lower:
                return False, f"Blocked word detected: {word}"
        return True, None

    async def check_output(self, text: str) -> tuple[bool, str | None]:
        """Check if output is safe. Returns (is_safe, reason)."""
        await asyncio.sleep(random.uniform(0.05, 0.1))
        if len(text) > 10000:
            return False, "Output too long"
        return True, None
