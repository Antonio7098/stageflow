"""Shared models for agent runtime orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, model_validator

@dataclass(frozen=True, slots=True)
class AgentConfig:
    """Configuration for the agent loop."""

    model: str = "mock-model"
    max_turns: int = 4
    max_validation_retries: int = 2
    temperature: float = 0.0
    max_tokens: int | None = None
    tool_calling_mode: str = "auto"


class AgentToolCall(BaseModel):
    """Structured tool call emitted by the model."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = None


class AgentTurn(BaseModel):
    """Validated single-turn agent decision."""

    thought: str | None = None
    tool_calls: list[AgentToolCall] = Field(default_factory=list)
    final_answer: str | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> AgentTurn:
        has_tools = bool(self.tool_calls)
        has_answer = bool(self.final_answer and self.final_answer.strip())
        if has_tools == has_answer:
            raise ValueError("Provide either tool_calls or final_answer")
        return self


class AgentToolResult(BaseModel):
    """Recorded result of a tool execution."""

    call_id: str
    name: str
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    child_runs: list[dict[str, Any]] = Field(default_factory=list)


class AgentRunResult(BaseModel):
    """Normalized result from a complete agent run."""

    response: str
    iterations: int
    prompt_name: str
    prompt_version: str
    llm: dict[str, Any]
    tool_results: list[AgentToolResult] = Field(default_factory=list)
    security: list[dict[str, Any]] = Field(default_factory=list)
    tool_calling_mode: str = "json"


__all__ = [
    "AgentConfig",
    "AgentRunResult",
    "AgentToolCall",
    "AgentToolResult",
    "AgentTurn",
]
