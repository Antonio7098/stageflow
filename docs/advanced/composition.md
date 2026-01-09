# Pipeline Composition

This guide covers advanced patterns for composing and extending pipelines.

## Merging Pipelines

### Basic Composition

Use `compose()` to merge two pipelines:

```python
from stageflow import Pipeline, StageKind

# Base pipeline
base = (
    Pipeline()
    .with_stage("input", InputStage, StageKind.TRANSFORM)
    .with_stage("process", ProcessStage, StageKind.TRANSFORM, dependencies=("input",))
)

# Extension pipeline
extension = (
    Pipeline()
    .with_stage("enrich", EnrichStage, StageKind.ENRICH)
    .with_stage("output", OutputStage, StageKind.TRANSFORM, dependencies=("process", "enrich"))
)

# Merged pipeline contains all stages
full = base.compose(extension)
```

### Stage Name Conflicts

When stage names conflict, the second pipeline wins:

```python
pipeline_a = Pipeline().with_stage("shared", StageA, StageKind.TRANSFORM)
pipeline_b = Pipeline().with_stage("shared", StageB, StageKind.TRANSFORM)

merged = pipeline_a.compose(pipeline_b)
# "shared" stage is now StageB
```

## Reusable Components

### Factory Functions

Create reusable pipeline components:

```python
def create_enrichment_component() -> Pipeline:
    """Reusable enrichment stages."""
    return (
        Pipeline()
        .with_stage("profile", ProfileEnrichStage(), StageKind.ENRICH)
        .with_stage("memory", MemoryEnrichStage(), StageKind.ENRICH)
        .with_stage("documents", DocumentEnrichStage(), StageKind.ENRICH)
    )

def create_guard_component() -> Pipeline:
    """Reusable guard stages."""
    return (
        Pipeline()
        .with_stage("input_guard", InputGuardStage(), StageKind.GUARD)
        .with_stage("output_guard", OutputGuardStage(), StageKind.GUARD)
    )

def create_chat_pipeline(llm_client) -> Pipeline:
    """Compose full chat pipeline from components."""
    return (
        create_guard_component()
        .compose(create_enrichment_component())
        .with_stage(
            "llm",
            LLMStage(llm_client),
            StageKind.TRANSFORM,
            dependencies=("input_guard", "profile", "memory"),
        )
        .with_stage(
            "output_guard",
            OutputGuardStage(),
            StageKind.GUARD,
            dependencies=("llm",),
        )
    )
```

### Parameterized Components

Create configurable components:

```python
def create_llm_component(
    model: str = "gpt-4",
    temperature: float = 0.7,
    dependencies: tuple[str, ...] = (),
) -> Pipeline:
    """Configurable LLM component."""
    return Pipeline().with_stage(
        "llm",
        LLMStage(model=model, temperature=temperature),
        StageKind.TRANSFORM,
        dependencies=dependencies,
    )

# Use with different configurations
fast_llm = create_llm_component(model="gpt-3.5-turbo", dependencies=("router",))
accurate_llm = create_llm_component(model="gpt-4", dependencies=("router", "enrich"))
```

## Pipeline Variants

### Feature Flags

Create pipeline variants based on features:

```python
def create_pipeline(features: set[str]) -> Pipeline:
    pipeline = Pipeline().with_stage("input", InputStage, StageKind.TRANSFORM)
    
    if "enrichment" in features:
        pipeline = pipeline.with_stage("enrich", EnrichStage, StageKind.ENRICH)
    
    if "guardrails" in features:
        pipeline = pipeline.with_stage(
            "guard",
            GuardStage,
            StageKind.GUARD,
            dependencies=("input",),
        )
    
    # LLM depends on whatever stages are present
    deps = ["input"]
    if "enrichment" in features:
        deps.append("enrich")
    if "guardrails" in features:
        deps.append("guard")
    
    pipeline = pipeline.with_stage(
        "llm",
        LLMStage,
        StageKind.TRANSFORM,
        dependencies=tuple(deps),
    )
    
    return pipeline

# Create variants
basic_pipeline = create_pipeline(set())
enriched_pipeline = create_pipeline({"enrichment"})
full_pipeline = create_pipeline({"enrichment", "guardrails"})
```

### Topology Variants

Create pipelines for different topologies:

```python
def create_fast_pipeline() -> Pipeline:
    """Optimized for speed."""
    return (
        Pipeline()
        .with_stage("router", FastRouterStage, StageKind.ROUTE)
        .with_stage("llm", FastLLMStage, StageKind.TRANSFORM, dependencies=("router",))
    )

def create_accurate_pipeline() -> Pipeline:
    """Optimized for accuracy."""
    return (
        Pipeline()
        .with_stage("router", AccurateRouterStage, StageKind.ROUTE)
        .with_stage("enrich", EnrichStage, StageKind.ENRICH)
        .with_stage(
            "llm",
            AccurateLLMStage,
            StageKind.TRANSFORM,
            dependencies=("router", "enrich"),
        )
        .with_stage("validate", ValidationStage, StageKind.GUARD, dependencies=("llm",))
    )

# Register both
from stageflow import pipeline_registry

pipeline_registry.register("chat_fast", create_fast_pipeline())
pipeline_registry.register("chat_accurate", create_accurate_pipeline())
```

## Dependency Injection

### Service Injection

Inject services into pipeline components:

```python
class PipelineBuilder:
    def __init__(
        self,
        llm_client,
        profile_service,
        memory_service,
        guard_service,
    ):
        self.llm_client = llm_client
        self.profile_service = profile_service
        self.memory_service = memory_service
        self.guard_service = guard_service
    
    def build_chat_pipeline(self) -> Pipeline:
        return (
            Pipeline()
            .with_stage("guard", InputGuardStage(self.guard_service), StageKind.GUARD)
            .with_stage("profile", ProfileEnrichStage(self.profile_service), StageKind.ENRICH)
            .with_stage("memory", MemoryEnrichStage(self.memory_service), StageKind.ENRICH)
            .with_stage(
                "llm",
                LLMStage(self.llm_client),
                StageKind.TRANSFORM,
                dependencies=("guard", "profile", "memory"),
            )
        )

# Production
builder = PipelineBuilder(
    llm_client=RealLLMClient(),
    profile_service=RealProfileService(),
    memory_service=RealMemoryService(),
    guard_service=RealGuardService(),
)
production_pipeline = builder.build_chat_pipeline()

# Testing
test_builder = PipelineBuilder(
    llm_client=MockLLMClient(),
    profile_service=MockProfileService(),
    memory_service=MockMemoryService(),
    guard_service=MockGuardService(),
)
test_pipeline = test_builder.build_chat_pipeline()
```

## Dynamic Pipelines

### Runtime Pipeline Selection

Select pipelines at runtime:

```python
from stageflow import pipeline_registry

def get_pipeline_for_request(request) -> Pipeline:
    # Select based on request attributes
        return pipeline_registry.get("voice_pipeline")
    elif request.execution_mode == "practice":
        return pipeline_registry.get("practice_pipeline")
    else:
        return pipeline_registry.get("default_pipeline")
```

### Conditional Stage Inclusion

Add stages conditionally:

```python
def create_adaptive_pipeline(ctx) -> Pipeline:
    pipeline = Pipeline().with_stage("input", InputStage, StageKind.TRANSFORM)
    
    # Add enrichment only for authenticated users
    if ctx.user_id:
        pipeline = pipeline.with_stage("profile", ProfileEnrichStage, StageKind.ENRICH)
    
    # Add premium features for pro users
    if ctx.plan_tier in ("pro", "enterprise"):
        pipeline = pipeline.with_stage("advanced", AdvancedStage, StageKind.TRANSFORM)
    
    return pipeline
```

## Best Practices

### 1. Keep Components Focused

Each component should have a single responsibility:

```python
# Good: Focused components
def create_auth_component(): ...
def create_enrichment_component(): ...
def create_processing_component(): ...

# Bad: Monolithic component
def create_everything_component(): ...
```

### 2. Document Dependencies

Make dependencies explicit in factory functions:

```python
def create_llm_component(
    dependencies: tuple[str, ...] = ("router", "enrich"),
) -> Pipeline:
    """Create LLM component.
    
    Args:
        dependencies: Stages that must complete before LLM.
                     Default: ("router", "enrich")
    """
    return Pipeline().with_stage(
        "llm",
        LLMStage,
        StageKind.TRANSFORM,
        dependencies=dependencies,
    )
```

### 3. Use Type Hints

Add type hints for better IDE support:

```python
from stageflow import Pipeline, StageKind

def create_pipeline(
    llm_client: LLMClient,
    features: set[str] | None = None,
) -> Pipeline:
    ...
```

### 4. Test Components Independently

Test each component in isolation:

```python
def test_enrichment_component():
    pipeline = create_enrichment_component()
    graph = pipeline.build()
    
    # Verify stages
    assert "profile" in [s.name for s in graph.stage_specs]
    assert "memory" in [s.name for s in graph.stage_specs]
```

## Next Steps

- [Subpipeline Runs](subpipelines.md) — Nested pipeline execution
- [Custom Interceptors](custom-interceptors.md) — Build middleware
- [Testing Strategies](testing.md) — Test your pipelines
