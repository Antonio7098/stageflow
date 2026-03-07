"""Helpers for attaching explicit metadata to stage classes."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from stageflow.core.stage_enums import StageKind

TStageClass = TypeVar("TStageClass", bound=type)


def stage_metadata(
    *,
    name: str,
    kind: StageKind | str,
) -> Callable[[TStageClass], TStageClass]:
    """Attach explicit Stageflow metadata to a stage class.

    This decorator is useful when you want to keep pipeline dependency wiring
    explicit in the pipeline definition while avoiding repeated `name = ...` and
    `kind = ...` assignments inside the class body.
    """
    resolved_kind = kind if isinstance(kind, StageKind) else StageKind(kind)

    def decorator(cls: TStageClass) -> TStageClass:
        setattr(cls, "name", name)
        setattr(cls, "kind", resolved_kind)
        return cls

    return decorator


__all__ = ["stage_metadata"]