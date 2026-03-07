"""Shared validation helpers for code-defined pipeline DAGs."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from typing import Any, Protocol

from stageflow.contracts import ContractErrorInfo
from stageflow.pipeline.spec import CycleDetectedError, PipelineValidationError


class DependencySpec(Protocol):
    """Minimal protocol for validating DAG dependencies."""

    name: str
    dependencies: tuple[str, ...]


def ensure_non_empty(stages: Mapping[str, DependencySpec], *, message: str) -> None:
    """Raise a structured validation error when no stages are defined."""
    if stages:
        return
    error_info = ContractErrorInfo(
        code="CONTRACT-004-EMPTY",
        summary="Cannot build a pipeline with zero stages",
        fix_hint="Add at least one stage before calling build().",
        doc_url="https://github.com/stageflow/stageflow/blob/main/docs/advanced/error-messages.md#empty-pipelines",
    )
    raise PipelineValidationError(message, error_info=error_info)


def validate_stage_dependencies(stages: Mapping[str, DependencySpec]) -> None:
    """Ensure all dependencies exist and the graph is acyclic."""
    for stage_name, spec in stages.items():
        for dep in spec.dependencies:
            if dep in stages:
                continue
            error_info = ContractErrorInfo(
                code="CONTRACT-004-MISSING_DEP",
                summary="Stage depends on an undefined dependency",
                fix_hint="Add the missing stage or remove it from the dependency list.",
                doc_url="https://github.com/stageflow/stageflow/blob/main/docs/advanced/error-messages.md#missing-stage-dependencies",
                context={"stage": stage_name, "dependency": dep},
            )
            raise PipelineValidationError(
                f"Stage '{stage_name}' depends on '{dep}' which does not exist",
                stages=[stage_name, dep],
                error_info=error_info,
            )
    _detect_cycles(stages)


def ensure_compatible_stage_specs(
    *,
    name: str,
    existing: Any,
    incoming: Any,
    attrs: tuple[str, ...],
) -> None:
    """Ensure two same-named stage specs are semantically compatible."""
    if all(getattr(existing, attr) == getattr(incoming, attr) for attr in attrs):
        return
    error_info = ContractErrorInfo(
        code="CONTRACT-004-CONFLICT",
        summary="Pipelines define conflicting stage specifications",
        fix_hint="Rename one of the stages or make the specs identical before composing.",
        doc_url="https://github.com/stageflow/stageflow/blob/main/docs/guides/stages.md#contract-troubleshooting",
        context={"stage": name},
    )
    raise PipelineValidationError(
        f"Cannot compose pipelines: stage '{name}' has different specs",
        stages=[name],
        error_info=error_info,
    )


def topologically_sorted_stage_names(stages: Mapping[str, DependencySpec]) -> list[str]:
    """Return stage names in topological order."""
    if not stages:
        return []
    in_degree = {name: len(set(spec.dependencies)) for name, spec in stages.items()}
    queue: deque[str] = deque(name for name, count in in_degree.items() if count == 0)
    ordered: list[str] = []

    while queue:
        node = queue.popleft()
        ordered.append(node)
        for name, spec in stages.items():
            if node not in spec.dependencies:
                continue
            in_degree[name] -= 1
            if in_degree[name] == 0:
                queue.append(name)
    return ordered


def _detect_cycles(stages: Mapping[str, DependencySpec]) -> None:
    if not stages:
        return

    white, gray, black = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(stages, white)

    def dfs(node: str, path: list[str]) -> list[str] | None:
        color[node] = gray
        path.append(node)
        for dep in stages[node].dependencies:
            if dep not in stages:
                continue
            if color[dep] == gray:
                cycle_start = path.index(dep)
                return path[cycle_start:] + [dep]
            if color[dep] == white:
                result = dfs(dep, path)
                if result:
                    return result
        path.pop()
        color[node] = black
        return None

    for name in stages:
        if color[name] != white:
            continue
        cycle_path = dfs(name, [])
        if cycle_path:
            raise CycleDetectedError(cycle_path=cycle_path, stages=list(dict.fromkeys(cycle_path)))


__all__ = [
    "DependencySpec",
    "ensure_compatible_stage_specs",
    "ensure_non_empty",
    "topologically_sorted_stage_names",
    "validate_stage_dependencies",
]