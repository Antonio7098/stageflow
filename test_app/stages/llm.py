"""LLM stage for real Groq integration."""

import asyncio
from typing import Any

from stageflow import StageContext, StageKind, StageOutput

from services.groq_client import GroqClient


class LLMStage:
    """Stage that calls Groq LLM for response generation."""

    name = "llm"
    kind = StageKind.TRANSFORM

    def __init__(self, groq_client: GroqClient | None = None):
        self.groq_client = groq_client or GroqClient()

    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs = ctx.config.get("inputs")

        if inputs:
            input_text = inputs.snapshot.input_text or ""
            profile = inputs.get("profile", {})
            memory = inputs.get("memory", {})
            messages = [m for m in inputs.snapshot.messages] if inputs.snapshot.messages else []
        else:
            input_text = ctx.snapshot.input_text or ""
            profile = {}
            memory = {}
            messages = list(ctx.snapshot.messages) if ctx.snapshot.messages else []

        system_prompt = self._build_system_prompt(profile, memory)

        llm_messages = [{"role": "system", "content": system_prompt}]

        for msg in messages[-10:]:
            llm_messages.append({
                "role": msg.role,
                "content": msg.content,
            })

        if input_text:
            llm_messages.append({"role": "user", "content": input_text})

        try:
            response = await self.groq_client.chat(
                messages=llm_messages,
                model="llama-3.1-8b-instant",
                temperature=0.7,
                max_tokens=1024,
            )
            return StageOutput.ok(
                response=response,
                model="llama-3.1-8b-instant",
                input_tokens=sum(len(m["content"]) for m in llm_messages),
            )
        except Exception as e:
            return StageOutput.fail(
                error=f"LLM call failed: {str(e)}",
                data={"error_type": type(e).__name__},
            )

    def _build_system_prompt(self, profile: dict, memory: dict) -> str:
        parts = ["You are a helpful AI assistant."]

        if profile:
            if profile.get("display_name"):
                parts.append(f"You're talking to {profile['display_name']}.")
            if profile.get("preferences"):
                tone = profile["preferences"].get("tone", "friendly")
                parts.append(f"Use a {tone} tone.")
            if profile.get("goals"):
                parts.append(f"Their goals: {', '.join(profile['goals'][:3])}")

        if memory:
            if memory.get("recent_topics"):
                parts.append(f"Recent topics discussed: {', '.join(memory['recent_topics'][:3])}")
            if memory.get("key_facts"):
                parts.append(f"Key facts: {'; '.join(memory['key_facts'][:3])}")

        return " ".join(parts)
