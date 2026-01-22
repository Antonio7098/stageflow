"""Delta compression utilities for ContextSnapshot-sized payloads."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "CompressionMetrics",
    "apply_delta",
    "compute_delta",
    "compress",
]


@dataclass(frozen=True)
class CompressionMetrics:
    """Basic stats for evaluating compression effectiveness."""

    original_bytes: int
    delta_bytes: int

    @property
    def reduction_bytes(self) -> int:
        return max(self.original_bytes - self.delta_bytes, 0)

    @property
    def ratio(self) -> float:
        if self.original_bytes == 0:
            return 1.0
        return self.delta_bytes / self.original_bytes


def compute_delta(base: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    """Compute a shallow delta describing changes between two dict-like objects."""

    set_ops: dict[str, Any] = {}
    remove_ops: list[str] = []

    for key, value in current.items():
        if key not in base or base[key] != value:
            set_ops[key] = value

    for key in base:
        if key not in current:
            remove_ops.append(key)

    delta: dict[str, Any] = {}
    if set_ops:
        delta["set"] = set_ops
    if remove_ops:
        delta["remove"] = remove_ops
    return delta


def apply_delta(base: Mapping[str, Any], delta: Mapping[str, Any]) -> dict[str, Any]:
    """Apply a previously generated delta to reconstruct the target dict."""

    result = dict(base)
    for key in delta.get("remove", []) or []:
        result.pop(key, None)
    for key, value in (delta.get("set") or {}).items():
        result[key] = value
    return result


def compress(base: Mapping[str, Any], current: Mapping[str, Any]) -> tuple[dict[str, Any], CompressionMetrics]:
    """Compute delta and metrics for the provided payloads."""

    delta = compute_delta(base, current)
    metrics = CompressionMetrics(
        original_bytes=_estimate_bytes(current),
        delta_bytes=_estimate_bytes(delta),
    )
    return delta, metrics


def _estimate_bytes(value: Any) -> int:
    try:
        data = json.dumps(value, ensure_ascii=False)
    except TypeError:
        data = json.dumps(_json_safe(value), ensure_ascii=False)
    return len(data.encode("utf-8"))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
