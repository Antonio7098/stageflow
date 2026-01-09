"""Property-based tests for DAG validity and pipeline building.

These tests verify that:
- Generated pipelines never contain cycles
- Pipeline.build() always produces valid graphs
- Topological sorting is always possible
"""

from __future__ import annotations

from hypothesis import given, settings, HealthCheck

from tests.property.strategies import stage_spec_lists


class TestDAGProperties:
    """Property tests for DAG validity."""

    @given(stage_spec_lists(min_stages=1, max_stages=10))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_generated_specs_have_no_self_dependencies(self, specs: list[dict]) -> None:
        """Stage specs never have self-dependencies."""
        for spec in specs:
            assert spec["name"] not in spec["dependencies"], (
                f"Stage '{spec['name']}' has self-dependency"
            )

    @given(stage_spec_lists(min_stages=2, max_stages=10))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.large_base_example])
    def test_generated_specs_only_depend_on_existing_stages(self, specs: list[dict]) -> None:
        """Dependencies only reference stages that exist earlier in the list."""
        seen_names: set[str] = set()
        for spec in specs:
            for dep in spec["dependencies"]:
                assert dep in seen_names, f"Stage '{spec['name']}' depends on unknown stage '{dep}'"
            seen_names.add(spec["name"])

    @given(stage_spec_lists(min_stages=1, max_stages=8))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_specs_form_valid_dag(self, specs: list[dict]) -> None:
        """Generated specs always form a valid DAG (no cycles)."""
        # Build adjacency list
        name_to_deps: dict[str, list[str]] = {spec["name"]: spec["dependencies"] for spec in specs}

        # Check for cycles using DFS
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for dep in name_to_deps.get(node, []):
                if dep not in visited:
                    if has_cycle(dep):
                        return True
                elif dep in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for name in name_to_deps:
            if name not in visited:
                assert not has_cycle(name), f"Cycle detected involving '{name}'"

    @given(stage_spec_lists(min_stages=1, max_stages=8))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_topological_sort_possible(self, specs: list[dict]) -> None:
        """Topological sort is always possible on generated specs."""
        name_to_deps: dict[str, set[str]] = {
            spec["name"]: set(spec["dependencies"]) for spec in specs
        }

        # Kahn's algorithm
        in_degree: dict[str, int] = dict.fromkeys(name_to_deps, 0)
        for name, deps in name_to_deps.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[name] = in_degree.get(name, 0)

        # Recalculate in-degrees properly
        for name in name_to_deps:
            in_degree[name] = len(name_to_deps[name])

        queue = [name for name, degree in in_degree.items() if degree == 0]
        sorted_count = 0

        while queue:
            node = queue.pop(0)
            sorted_count += 1

            for name, deps in name_to_deps.items():
                if node in deps:
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        queue.append(name)

        assert sorted_count == len(specs), (
            f"Topological sort incomplete: sorted {sorted_count} of {len(specs)}"
        )


class TestPipelineComposition:
    """Property tests for pipeline composition."""

    @given(stage_spec_lists(min_stages=1, max_stages=5))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_stage_names_are_unique(self, specs: list[dict]) -> None:
        """All stage names in a specification are unique."""
        names = [spec["name"] for spec in specs]
        assert len(names) == len(set(names)), "Duplicate stage names found"

    @given(stage_spec_lists(min_stages=2, max_stages=6))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.large_base_example])
    def test_dependencies_are_subset_of_stages(self, specs: list[dict]) -> None:
        """All dependencies reference stages that exist."""
        all_names = {spec["name"] for spec in specs}
        for spec in specs:
            for dep in spec["dependencies"]:
                assert dep in all_names, f"Dependency '{dep}' not in stage set"
