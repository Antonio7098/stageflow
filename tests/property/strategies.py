"""Hypothesis strategies for stageflow property-based tests.

This module provides strategies for generating:
- Stage names and specifications
- Pipelines with valid DAG structures
- Events and event sequences
- Context keys and values
"""

from __future__ import annotations

import string
from typing import Any
from uuid import uuid4

from hypothesis import strategies as st
from hypothesis.strategies import composite

from stageflow import StageKind


# Basic strategies


@st.composite
def stage_names(draw: Any) -> str:
    """Generate valid stage names."""
    first_char = draw(st.sampled_from(string.ascii_lowercase))
    rest = draw(st.text(
        alphabet=string.ascii_lowercase + string.digits + "_",
        min_size=2,
        max_size=20,
    ))
    return first_char + rest


@st.composite
def stage_kinds(draw: Any) -> StageKind:
    """Generate stage kinds."""
    return draw(st.sampled_from(list(StageKind)))


@st.composite
def uuids(draw: Any) -> Any:
    """Generate UUIDs."""
    return uuid4()


# Stage specification strategies


@st.composite
def stage_specs(draw: Any, max_deps: int = 3) -> dict[str, Any]:
    """Generate a valid stage specification.

    Args:
        max_deps: Maximum number of dependencies per stage

    Returns:
        Dict with name, kind, and dependencies
    """
    name = draw(stage_names())
    kind = draw(stage_kinds())

    return {
        "name": name,
        "kind": kind,
        "dependencies": [],  # Will be filled by pipeline generator
    }


@st.composite
def stage_spec_lists(
    draw: Any,
    min_stages: int = 1,
    max_stages: int = 10,
) -> list[dict[str, Any]]:
    """Generate a list of stage specs with valid dependencies.

    Ensures no cycles by only allowing dependencies on earlier stages.
    """
    num_stages = draw(st.integers(min_value=min_stages, max_value=max_stages))

    specs = []
    used_names: set[str] = set()

    for i in range(num_stages):
        # Generate unique name
        name = draw(stage_names())
        while name in used_names:
            name = draw(stage_names())
        used_names.add(name)

        kind = draw(stage_kinds())

        # Only depend on earlier stages (ensures no cycles)
        available_deps = [s["name"] for s in specs]
        if available_deps:
            num_deps = draw(st.integers(min_value=0, max_value=min(3, len(available_deps))))
            deps = draw(st.lists(
                st.sampled_from(available_deps),
                min_size=0,
                max_size=num_deps,
                unique=True,
            ))
        else:
            deps = []

        specs.append({
            "name": name,
            "kind": kind,
            "dependencies": deps,
        })

    return specs


# Context strategies


@st.composite
def context_keys(draw: Any) -> str:
    """Generate valid context keys."""
    return draw(st.text(
        alphabet=string.ascii_lowercase + string.digits + "_",
        min_size=1,
        max_size=50,
    ).filter(lambda x: x[0].isalpha()))


@st.composite
def context_values(draw: Any) -> Any:
    """Generate serializable context values."""
    return draw(st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-1000000, max_value=1000000),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(min_size=0, max_size=100),
        st.lists(st.integers(), min_size=0, max_size=10),
        st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(st.integers(), st.text(max_size=20)),
            min_size=0,
            max_size=5,
        ),
    ))


# Event strategies


@st.composite
def event_types(draw: Any) -> str:
    """Generate valid event type strings."""
    prefix = draw(st.sampled_from(["stage", "tool", "pipeline", "approval"]))
    name = draw(stage_names())
    status = draw(st.sampled_from(["started", "completed", "failed", "invoked"]))
    return f"{prefix}.{name}.{status}"


@st.composite
def events(draw: Any) -> dict[str, Any]:
    """Generate event dictionaries."""
    return {
        "type": draw(event_types()),
        "timestamp": "2024-01-01T00:00:00Z",
        "data": draw(st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=context_values(),
            min_size=0,
            max_size=5,
        )),
    }


@st.composite
def event_sequences(draw: Any, min_events: int = 1, max_events: int = 20) -> list[dict[str, Any]]:
    """Generate event sequences with monotonic sequence numbers."""
    num_events = draw(st.integers(min_value=min_events, max_value=max_events))
    sequence = []

    for i in range(num_events):
        event = draw(events())
        event["sequence"] = i + 1
        sequence.append(event)

    return sequence


# Behavior strategies


@st.composite
def behaviors(draw: Any) -> str:
    """Generate execution behavior/mode strings."""
    return draw(st.sampled_from([
        "practice",
        "roleplay",
        "doc_edit",
        "assessment",
        "conversation",
        "test",
    ]))


@st.composite
def behavior_tuples(draw: Any, min_size: int = 0, max_size: int = 4) -> tuple[str, ...]:
    """Generate tuples of allowed behaviors."""
    behaviors_list = draw(st.lists(
        behaviors(),
        min_size=min_size,
        max_size=max_size,
        unique=True,
    ))
    return tuple(behaviors_list)


__all__ = [
    # Basic
    "stage_names",
    "stage_kinds",
    "uuids",
    # Stage specs
    "stage_specs",
    "stage_spec_lists",
    # Context
    "context_keys",
    "context_values",
    # Events
    "event_types",
    "events",
    "event_sequences",
    # Behaviors
    "behaviors",
    "behavior_tuples",
]
