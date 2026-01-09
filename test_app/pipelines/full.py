"""Full feature pipeline - tests all stageflow features."""

from stageflow import Pipeline, StageKind

from stages.router import RouterStage
from stages.guard import InputGuardStage, OutputGuardStage
from stages.enrich import ProfileEnrichStage, MemoryEnrichStage
from stages.llm import LLMStage
from services.groq_client import GroqClient


def create_full_pipeline(groq_client: GroqClient | None = None) -> Pipeline:
    """Create a full-featured pipeline with all stage types.
    
    DAG:
        [input_guard] -> [router] ─┐
                                   │
        [profile_enrich] ──────────┼─> [llm] -> [output_guard]
                                   │
        [memory_enrich] ───────────┘
    
    Features tested:
    - Guard stages (input/output validation)
    - Route stages (path selection)
    - Enrich stages (parallel context enrichment)
    - Transform stages (LLM processing)
    - Dependencies (linear and fan-in)
    """
    return (
        Pipeline()
        # Input guard runs first
        .with_stage(
            name="input_guard",
            runner=InputGuardStage(),
            kind=StageKind.GUARD,
        )
        # Router decides path after guard
        .with_stage(
            name="router",
            runner=RouterStage,
            kind=StageKind.ROUTE,
            dependencies=("input_guard",),
        )
        # Parallel enrichment stages (no deps on each other)
        .with_stage(
            name="profile_enrich",
            runner=ProfileEnrichStage(),
            kind=StageKind.ENRICH,
        )
        .with_stage(
            name="memory_enrich",
            runner=MemoryEnrichStage(),
            kind=StageKind.ENRICH,
        )
        # LLM waits for routing and enrichment
        .with_stage(
            name="llm",
            runner=LLMStage(groq_client=groq_client),
            kind=StageKind.TRANSFORM,
            dependencies=("router", "profile_enrich", "memory_enrich"),
        )
        # Output guard validates LLM response
        .with_stage(
            name="output_guard",
            runner=OutputGuardStage(),
            kind=StageKind.GUARD,
            dependencies=("llm",),
        )
    )
