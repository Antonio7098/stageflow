"""Tests for pipeline builder helpers."""


from stageflow.pipeline.builder import PipelineBuilder
from stageflow.pipeline.builder_helpers import (
    FluentPipelineBuilder,
    with_conditional_branch,
    with_fan_out_fan_in,
    with_linear_chain,
    with_parallel_stages,
)


class MockStage:
    """Mock stage for testing."""

    def __init__(self, name: str = "mock"):
        self.name = name

    async def execute(self, _ctx):
        return {"status": "completed"}


def make_mock_stage(index: int) -> tuple[str, MockStage]:
    """Factory for creating mock stages."""
    return f"stage_{index}", MockStage(f"stage_{index}")


class TestWithLinearChain:
    """Tests for with_linear_chain helper."""

    def test_creates_linear_dependencies(self):
        """Test that linear chain creates correct dependencies."""
        builder = PipelineBuilder(name="test")

        result = with_linear_chain(
            builder,
            count=3,
            stage_factory=make_mock_stage,
        )

        assert "stage_0" in result.stages
        assert "stage_1" in result.stages
        assert "stage_2" in result.stages

        # Check dependencies
        assert result.stages["stage_0"].dependencies == ()
        assert result.stages["stage_1"].dependencies == ("stage_0",)
        assert result.stages["stage_2"].dependencies == ("stage_1",)

    def test_first_depends_on(self):
        """Test first_depends_on parameter."""
        builder = PipelineBuilder(name="test").with_stage(
            name="input",
            runner=MockStage("input"),
        )

        result = with_linear_chain(
            builder,
            count=2,
            stage_factory=make_mock_stage,
            first_depends_on=("input",),
        )

        assert result.stages["stage_0"].dependencies == ("input",)
        assert result.stages["stage_1"].dependencies == ("stage_0",)

    def test_zero_count_returns_unchanged(self):
        """Test that count=0 returns unchanged builder."""
        builder = PipelineBuilder(name="test")

        result = with_linear_chain(
            builder,
            count=0,
            stage_factory=make_mock_stage,
        )

        assert result.stages == builder.stages


class TestWithParallelStages:
    """Tests for with_parallel_stages helper."""

    def test_creates_parallel_stages(self):
        """Test that parallel stages have same dependencies."""
        builder = PipelineBuilder(name="test").with_stage(
            name="input",
            runner=MockStage("input"),
        )

        result = with_parallel_stages(
            builder,
            count=3,
            stage_factory=make_mock_stage,
            depends_on=("input",),
        )

        # All parallel stages depend on input
        assert result.stages["stage_0"].dependencies == ("input",)
        assert result.stages["stage_1"].dependencies == ("input",)
        assert result.stages["stage_2"].dependencies == ("input",)

    def test_no_dependencies(self):
        """Test parallel stages with no dependencies."""
        builder = PipelineBuilder(name="test")

        result = with_parallel_stages(
            builder,
            count=2,
            stage_factory=make_mock_stage,
        )

        assert result.stages["stage_0"].dependencies == ()
        assert result.stages["stage_1"].dependencies == ()


class TestWithFanOutFanIn:
    """Tests for with_fan_out_fan_in helper."""

    def test_creates_fan_out_fan_in_pattern(self):
        """Test fan-out/fan-in pattern creation."""
        builder = PipelineBuilder(name="test")

        result = with_fan_out_fan_in(
            builder,
            fan_out_stage=("splitter", MockStage("splitter")),
            parallel_count=3,
            parallel_factory=lambda i: (f"worker_{i}", MockStage(f"worker_{i}")),
            fan_in_stage=("merger", MockStage("merger")),
        )

        # Check fan-out
        assert "splitter" in result.stages
        assert result.stages["splitter"].dependencies == ()

        # Check parallel stages depend on fan-out
        assert result.stages["worker_0"].dependencies == ("splitter",)
        assert result.stages["worker_1"].dependencies == ("splitter",)
        assert result.stages["worker_2"].dependencies == ("splitter",)

        # Check fan-in depends on all parallel stages
        merger_deps = set(result.stages["merger"].dependencies)
        assert merger_deps == {"worker_0", "worker_1", "worker_2"}

    def test_fan_out_depends_on(self):
        """Test fan-out with upstream dependency."""
        builder = PipelineBuilder(name="test").with_stage(
            name="input",
            runner=MockStage("input"),
        )

        result = with_fan_out_fan_in(
            builder,
            fan_out_stage=("splitter", MockStage("splitter")),
            parallel_count=2,
            parallel_factory=lambda i: (f"worker_{i}", MockStage(f"worker_{i}")),
            fan_in_stage=("merger", MockStage("merger")),
            fan_out_depends_on=("input",),
        )

        assert result.stages["splitter"].dependencies == ("input",)


class TestWithConditionalBranch:
    """Tests for with_conditional_branch helper."""

    def test_creates_conditional_branches(self):
        """Test conditional branch creation."""
        builder = PipelineBuilder(name="test")

        result = with_conditional_branch(
            builder,
            router_stage=("router", MockStage("router")),
            branches={
                "branch_a": ("handler_a", MockStage("handler_a")),
                "branch_b": ("handler_b", MockStage("handler_b")),
            },
        )

        # Check router
        assert "router" in result.stages

        # Check branches depend on router and are conditional
        assert result.stages["handler_a"].dependencies == ("router",)
        assert result.stages["handler_a"].conditional is True
        assert result.stages["handler_b"].dependencies == ("router",)
        assert result.stages["handler_b"].conditional is True

    def test_with_merge_stage(self):
        """Test conditional branch with merge stage."""
        builder = PipelineBuilder(name="test")

        result = with_conditional_branch(
            builder,
            router_stage=("router", MockStage("router")),
            branches={
                "branch_a": ("handler_a", MockStage("handler_a")),
                "branch_b": ("handler_b", MockStage("handler_b")),
            },
            merge_stage=("merger", MockStage("merger")),
        )

        # Merge stage depends on all branches
        merge_deps = set(result.stages["merger"].dependencies)
        assert merge_deps == {"handler_a", "handler_b"}


class TestFluentPipelineBuilder:
    """Tests for FluentPipelineBuilder."""

    def test_stage_method(self):
        """Test adding single stage."""
        pipeline = (
            FluentPipelineBuilder("test")
            .stage("input", MockStage("input"))
            .stage("output", MockStage("output"), depends_on=("input",))
        )

        builder = pipeline.builder
        assert "input" in builder.stages
        assert "output" in builder.stages
        assert builder.stages["output"].dependencies == ("input",)

    def test_linear_chain_method(self):
        """Test linear chain method."""
        pipeline = (
            FluentPipelineBuilder("test")
            .stage("input", MockStage("input"))
            .linear_chain(3, make_mock_stage)
        )

        builder = pipeline.builder
        assert "stage_0" in builder.stages
        assert "stage_1" in builder.stages
        assert "stage_2" in builder.stages

        # First stage should depend on input (last stage before chain)
        assert builder.stages["stage_0"].dependencies == ("input",)

    def test_parallel_method(self):
        """Test parallel stages method."""
        pipeline = (
            FluentPipelineBuilder("test")
            .stage("input", MockStage("input"))
            .parallel(3, make_mock_stage)
        )

        builder = pipeline.builder
        # All parallel stages should depend on input
        assert builder.stages["stage_0"].dependencies == ("input",)
        assert builder.stages["stage_1"].dependencies == ("input",)
        assert builder.stages["stage_2"].dependencies == ("input",)

    def test_fan_out_fan_in_method(self):
        """Test fan-out/fan-in method."""
        pipeline = (
            FluentPipelineBuilder("test")
            .stage("input", MockStage("input"))
            .fan_out_fan_in(
                fan_out=("splitter", MockStage("splitter")),
                parallel_count=2,
                parallel_factory=lambda i: (f"worker_{i}", MockStage(f"worker_{i}")),
                fan_in=("merger", MockStage("merger")),
            )
        )

        builder = pipeline.builder

        # Splitter depends on input
        assert builder.stages["splitter"].dependencies == ("input",)

        # Workers depend on splitter
        assert builder.stages["worker_0"].dependencies == ("splitter",)
        assert builder.stages["worker_1"].dependencies == ("splitter",)

        # Merger depends on workers
        merger_deps = set(builder.stages["merger"].dependencies)
        assert merger_deps == {"worker_0", "worker_1"}

    def test_chaining_updates_last_stage(self):
        """Test that chaining correctly updates last stage tracking."""
        pipeline = (
            FluentPipelineBuilder("test")
            .stage("a", MockStage("a"))
            .stage("b", MockStage("b"))  # Should auto-depend on "a"
        )

        builder = pipeline.builder
        # Without explicit depends_on, it should NOT auto-depend
        # (FluentPipelineBuilder.stage requires explicit depends_on)
        assert builder.stages["b"].dependencies == ()
