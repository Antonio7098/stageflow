"""Enrichment stages for testing parallel execution."""


from services.mocks import MockMemoryService, MockProfileService

from stageflow import StageContext, StageKind, StageOutput


class ProfileEnrichStage:
    """Enrich context with user profile information."""

    name = "profile_enrich"
    kind = StageKind.ENRICH

    def __init__(self, profile_service: MockProfileService | None = None):
        self.profile_service = profile_service or MockProfileService()

    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs = ctx.config.get("inputs")
        user_id = inputs.snapshot.user_id if inputs else ctx.snapshot.user_id

        if not user_id:
            return StageOutput.skip(reason="No user_id provided")

        profile = await self.profile_service.get_profile(user_id)

        return StageOutput.ok(
            profile={
                "user_id": str(profile.user_id),
                "display_name": profile.display_name,
                "preferences": profile.preferences,
                "goals": profile.goals,
            }
        )


class MemoryEnrichStage:
    """Enrich context with conversation memory."""

    name = "memory_enrich"
    kind = StageKind.ENRICH

    def __init__(self, memory_service: MockMemoryService | None = None):
        self.memory_service = memory_service or MockMemoryService()

    async def execute(self, ctx: StageContext) -> StageOutput:
        inputs = ctx.config.get("inputs")
        session_id = inputs.snapshot.session_id if inputs else ctx.snapshot.session_id

        if not session_id:
            return StageOutput.skip(reason="No session_id provided")

        memory = await self.memory_service.get_memory(session_id)

        return StageOutput.ok(
            memory={
                "recent_topics": memory.recent_topics,
                "key_facts": memory.key_facts,
                "interaction_count": memory.interaction_count,
            }
        )
