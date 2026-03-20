"""Canonical observability event taxonomy for Stageflow.

This module defines the baseline event kinds shared across the framework so
that telemetry payloads can be grouped consistently regardless of the emitter.
"""

from __future__ import annotations

from enum import Enum

# Increment this if the canonical metadata envelope changes shape.
EVENT_VERSION = "v1"


class EventKind(str, Enum):
    """High-level categories for observability events."""

    TRACE = "trace"
    SPAN = "span"
    GENERATION = "generation"
    TOOL = "tool"
    AGENT = "agent"
    EVALUATOR = "evaluator"


__all__ = [
    "EVENT_VERSION",
    "EventKind",
]
