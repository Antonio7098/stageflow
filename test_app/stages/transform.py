"""Transform stages for testing data transformation."""

import asyncio

from stageflow import StageContext, StageKind, StageOutput


class UppercaseStage:
    """Transform text to uppercase."""

    name = "uppercase"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        await asyncio.sleep(0.15)

        inputs = ctx.config.get("inputs")
        if inputs:
            text = inputs.get("text") or inputs.snapshot.input_text or ""
        else:
            text = ctx.snapshot.input_text or ""

        result = text.upper()
        return StageOutput.ok(text=result, transformed=True)


class ReverseStage:
    """Reverse the text."""

    name = "reverse"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        await asyncio.sleep(0.15)

        inputs = ctx.config.get("inputs")
        if inputs:
            text = inputs.get("text") or inputs.snapshot.input_text or ""
        else:
            text = ctx.snapshot.input_text or ""

        result = text[::-1]
        return StageOutput.ok(text=result, reversed=True)


class SummarizeStage:
    """Summarize/truncate text (mock summarization)."""

    name = "summarize"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        await asyncio.sleep(0.2)

        inputs = ctx.config.get("inputs")
        if inputs:
            text = inputs.get("text") or inputs.snapshot.input_text or ""
        else:
            text = ctx.snapshot.input_text or ""

        if len(text) > 100:
            summary = text[:100] + "..."
        else:
            summary = text

        return StageOutput.ok(
            text=summary,
            summary=summary,
            original_length=len(text),
            summarized=True,
        )


class InsightsStage:
    """Combine enrichment outputs into human-readable insights."""

    name = "insights"
    kind = StageKind.TRANSFORM

    async def execute(self, ctx: StageContext) -> StageOutput:
        await asyncio.sleep(0.1)

        inputs = ctx.config.get("inputs")
        profile = inputs.get("profile", {}) if inputs else {}
        memory = inputs.get("memory", {}) if inputs else {}

        bullet_points: list[str] = []
        display_name = profile.get("display_name")
        preferences = profile.get("preferences") or []
        goals = profile.get("goals") or []
        recent_topics = memory.get("recent_topics") or []
        key_facts = memory.get("key_facts") or []

        if display_name:
            bullet_points.append(f"User identified as {display_name}.")
        if preferences:
            pref_list = ", ".join(preferences[:3])
            bullet_points.append(f"Top interests: {pref_list}.")
        if goals:
            goal_list = "; ".join(goals[:2])
            bullet_points.append(f"Current goals: {goal_list}.")
        if recent_topics:
            bullet_points.append(
                f"Recently discussed topics: {', '.join(recent_topics[:3])}."
            )
        if key_facts:
            bullet_points.append(
                f"Key facts remembered: {', '.join(key_facts[:3])}."
            )

        if not bullet_points:
            bullet_points.append("No contextual insights were available.")

        insights_text = "\n".join(f"- {point}" for point in bullet_points)

        return StageOutput.ok(
            insights=bullet_points,
            insights_text=insights_text,
            summarized_profile=profile,
            summarized_memory=memory,
        )


class FollowUpStage:
    """Generate follow-up suggestions based on insights."""

    name = "follow_up"
    kind = StageKind.WORK

    def __init__(self, max_questions: int = 3):
        self.max_questions = max_questions

    async def execute(self, ctx: StageContext) -> StageOutput:
        await asyncio.sleep(0.1)

        inputs = ctx.config.get("inputs")
        insights_text = inputs.get("insights_text", "") if inputs else ""
        snapshot = inputs.snapshot if inputs else ctx.snapshot
        user_input = snapshot.input_text or ""

        base_questions = [
            "What would you like to focus on next?",
            "Would you like to dig deeper into any of these insights?",
            "Is there new information I should consider for our next step?",
        ]

        if user_input:
            base_questions.insert(
                0, f"Can you elaborate on \"{user_input[:60]}\"?"
            )

        follow_up_questions = base_questions[: self.max_questions]

        response = (
            "Here are the latest personalized insights:\n\n"
            f"{insights_text or '- No insights available.'}\n\n"
            "Let me know how you'd like to continue."
        )

        return StageOutput.ok(
            response=response,
            follow_up_questions=follow_up_questions,
            insights_acknowledged=bool(insights_text.strip()),
        )
