"""Pipeline definitions for the test app."""

from .agent_demo import create_agent_demo_pipeline
from .full import create_full_pipeline
from .insights import (
    create_guarded_insights_pipeline,
    create_insights_pipeline,
)
from .llm import create_llm_pipeline
from .observability_demo import create_observability_demo_pipeline
from .parallel import create_parallel_pipeline
from .simple import create_simple_pipeline
from .transform import create_transform_pipeline
from .unified_tools import create_unified_tools_pipeline

PIPELINES = {
    "simple": {
        "name": "Simple Echo",
        "description": "Single stage that echoes input",
        "create": create_simple_pipeline,
        "instructions": "Type any message and the echo stage will replay it back verbatim.",
    },
    "transform": {
        "name": "Transform Chain",
        "description": "Linear chain of transform stages",
        "create": create_transform_pipeline,
        "instructions": "Provide text to see sequential transformations applied by each stage.",
    },
    "parallel": {
        "name": "Parallel Enrich",
        "description": "Parallel enrichment stages",
        "create": create_parallel_pipeline,
        "instructions": "Send input to watch multiple enrichment stages run concurrently.",
    },
    "llm": {
        "name": "LLM Chat",
        "description": "Real LLM integration with Groq",
        "create": create_llm_pipeline,
        "instructions": "Chat naturally—messages are routed to Groq's LLM and responses stream back.",
    },
    "full": {
        "name": "Full Pipeline",
        "description": "Complete pipeline with all features",
        "create": create_full_pipeline,
        "instructions": "Demonstrates the entire stack—send any message to exercise guards, enrichers, and the LLM.",
    },
    "insights": {
        "name": "Insights Builder",
        "description": "Enrichment fan-in with insights & follow-ups",
        "create": create_insights_pipeline,
        "instructions": "Ask for a summary or insights about a topic to see enrichment + synthesis.",
    },
    "insights_guarded": {
        "name": "Guarded Insights",
        "description": "Guards + enrichment -> insights -> follow-ups",
        "create": create_guarded_insights_pipeline,
        "instructions": "Same as Insights but includes guardrails—try both safe and unsafe prompts.",
    },
    "agent_demo": {
        "name": "Agent Tools Demo",
        "description": "Agent with toggle tool and subpipeline routing",
        "create": create_agent_demo_pipeline,
        "instructions": "Say “turn it on/off” to toggle the panel. Mention “subpipeline” to force the worker path.",
    },
    "unified_tools": {
        "name": "Unified Tools",
        "description": "Advanced tool executor with observability and behavior gating",
        "create": create_unified_tools_pipeline,
        "instructions": "Include keywords like “echo”, “transform”, “validate”, or “restricted” to trigger specific tools.",
    },
    "observability_demo": {
        "name": "Observability Demo",
        "description": "Input parser, compute, format, and aggregation with rich events",
        "create": create_observability_demo_pipeline,
        "instructions": "Provide any sentence to see parsing, computed metrics, and a formatted summary.",
    },
}

__all__ = [
    "PIPELINES",
    "create_simple_pipeline",
    "create_transform_pipeline",
    "create_parallel_pipeline",
    "create_llm_pipeline",
    "create_full_pipeline",
    "create_insights_pipeline",
    "create_guarded_insights_pipeline",
    "create_agent_demo_pipeline",
    "create_unified_tools_pipeline",
    "create_observability_demo_pipeline",
]
