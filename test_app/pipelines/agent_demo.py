"""Pipeline demonstrating agent tools and subpipeline routing."""

from stageflow import Pipeline, StageKind

from stages import AgentStage, SubpipelineStage, DispatchStage


def create_agent_demo_pipeline() -> Pipeline:
    """Create a pipeline with agent tools and subpipeline routing.

    This pipeline demonstrates:
    - Agent stage with tool execution (toggle panel)
    - Dispatch stage for conditional routing
    - Subpipeline stage for child pipeline simulation

    DAG:
        [dispatch] -> [agent]
                  -> [subpipeline]
    """
    return (
        Pipeline()
        .with_stage(
            name="dispatch",
            runner=DispatchStage,
            kind=StageKind.ROUTE,
        )
        .with_stage(
            name="agent",
            runner=AgentStage,
            kind=StageKind.TRANSFORM,
            dependencies=("dispatch",),
            conditional=True,
        )
        .with_stage(
            name="subpipeline",
            runner=SubpipelineStage,
            kind=StageKind.TRANSFORM,
            dependencies=("dispatch",),
            conditional=True,
        )
    )


__all__ = ["create_agent_demo_pipeline"]
