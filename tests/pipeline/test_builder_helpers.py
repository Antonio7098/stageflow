"""Tests for pipeline builder helpers."""


from stageflow.pipeline.builder import PipelineBuilder
from stageflow.pipeline.builder_helpers import (
    DuplexLaneSpec,
    DuplexSystemSpec,
    FluentPipelineBuilder,
    with_conditional_branch,
    with_duplex_system,
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


class TestWithDuplexSystem:
    """Tests for with_duplex_system helper."""

    def test_creates_bidirectional_lanes_with_join(self):
        """Test duplex helper wires independent lanes and an optional join stage."""
        builder = (
            PipelineBuilder(name="test")
            .with_stage(name="ingress_a", runner=MockStage("ingress_a"))
            .with_stage(name="ingress_b", runner=MockStage("ingress_b"))
        )
        system = DuplexSystemSpec(
            forward=DuplexLaneSpec(
                stages=(
                    ("uplink_0", MockStage("uplink_0")),
                    ("uplink_1", MockStage("uplink_1")),
                ),
                depends_on=("ingress_a",),
            ),
            reverse=DuplexLaneSpec(
                stages=(
                    ("downlink_0", MockStage("downlink_0")),
                    ("downlink_1", MockStage("downlink_1")),
                ),
                depends_on=("ingress_b",),
            ),
            join_stage=("sync", MockStage("sync")),
        )

        result = with_duplex_system(builder, system)

        assert result.stages["uplink_0"].dependencies == ("ingress_a",)
        assert result.stages["uplink_1"].dependencies == ("uplink_0",)
        assert result.stages["downlink_0"].dependencies == ("ingress_b",)
        assert result.stages["downlink_1"].dependencies == ("downlink_0",)
        assert result.stages["sync"].dependencies == ("uplink_1", "downlink_1")

    def test_join_depends_on_appends_extra_dependencies(self):
        """Test join stage can depend on lane tails plus extra stages."""
        builder = PipelineBuilder(name="test").with_stage(
            name="audit",
            runner=MockStage("audit"),
        )
        system = DuplexSystemSpec(
            forward=DuplexLaneSpec(stages=(("fwd", MockStage("fwd")),)),
            reverse=DuplexLaneSpec(stages=(("rev", MockStage("rev")),)),
            join_stage=("sync", MockStage("sync")),
            join_depends_on=("audit", "fwd"),  # duplicate fwd should be deduped
        )

        result = with_duplex_system(builder, system)
        assert result.stages["sync"].dependencies == ("fwd", "rev", "audit")

    def test_rejects_duplicate_stage_names(self):
        """Test duplicate names inside duplex lanes are rejected."""
        builder = PipelineBuilder(name="test")
        system = DuplexSystemSpec(
            forward=DuplexLaneSpec(stages=(("shared", MockStage("shared")),)),
            reverse=DuplexLaneSpec(stages=(("shared", MockStage("shared-2")),)),
        )

        try:
            with_duplex_system(builder, system)
            raise AssertionError("Expected ValueError for duplicate stage names")
        except ValueError as exc:
            assert "duplicate stage names" in str(exc)

    def test_rejects_collisions_with_existing_builder_stages(self):
        """Test helper fails fast when new names already exist in pipeline."""
        builder = PipelineBuilder(name="test").with_stage(
            name="existing",
            runner=MockStage("existing"),
        )
        system = DuplexSystemSpec(
            forward=DuplexLaneSpec(stages=(("existing", MockStage("fwd")),)),
            reverse=DuplexLaneSpec(stages=(("rev", MockStage("rev")),)),
        )

        try:
            with_duplex_system(builder, system)
            raise AssertionError("Expected ValueError for stage collisions")
        except ValueError as exc:
            assert "already exist" in str(exc)

    def test_lane_requires_at_least_one_stage(self):
        """Test empty lanes are rejected by DuplexLaneSpec."""
        try:
            DuplexLaneSpec(stages=())
            raise AssertionError("Expected ValueError for empty lane")
        except ValueError as exc:
            assert "at least one stage" in str(exc)


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

    def test_duplex_method_uses_last_stage_for_both_lanes(self):
        """Test fluent duplex auto-wires to the previous fluent tail stage."""
        pipeline = (
            FluentPipelineBuilder("test")
            .stage("entry", MockStage("entry"))
            .duplex(
                forward=(("fwd_0", MockStage("fwd_0")), ("fwd_1", MockStage("fwd_1"))),
                reverse=(("rev_0", MockStage("rev_0")),),
                join_stage=("sync", MockStage("sync")),
            )
        )

        builder = pipeline.builder
        assert builder.stages["fwd_0"].dependencies == ("entry",)
        assert builder.stages["fwd_1"].dependencies == ("fwd_0",)
        assert builder.stages["rev_0"].dependencies == ("entry",)
        assert builder.stages["sync"].dependencies == ("fwd_1", "rev_0")

    def test_duplex_method_updates_last_stage_for_followup_helpers(self):
        """Test fluent duplex join stage becomes the next auto dependency source."""
        pipeline = (
            FluentPipelineBuilder("test")
            .stage("entry", MockStage("entry"))
            .duplex(
                forward=(("fwd", MockStage("fwd")),),
                reverse=(("rev", MockStage("rev")),),
                join_stage=("sync", MockStage("sync")),
            )
            .linear_chain(1, make_mock_stage)
        )

        builder = pipeline.builder
        assert builder.stages["stage_0"].dependencies == ("sync",)
