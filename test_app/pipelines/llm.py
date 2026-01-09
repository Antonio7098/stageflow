"""LLM chat pipeline - tests real LLM integration."""

from stageflow import Pipeline, StageKind

from stages.guard import InputGuardStage
from stages.llm import LLMStage
from services.groq_client import GroqClient


def create_llm_pipeline(groq_client: GroqClient | None = None) -> Pipeline:
    """Create a pipeline with LLM integration.
    
    DAG:
        [input_guard] -> [llm]
    """
    return (
        Pipeline()
        .with_stage(
            name="input_guard",
            runner=InputGuardStage(),
            kind=StageKind.GUARD,
        )
        .with_stage(
            name="llm",
            runner=LLMStage(groq_client=groq_client),
            kind=StageKind.TRANSFORM,
            dependencies=("input_guard",),
        )
    )
