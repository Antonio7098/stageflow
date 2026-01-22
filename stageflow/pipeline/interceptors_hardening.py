"""Hardening interceptors for runtime safety and resource monitoring.

These interceptors provide deeper validation and monitoring than the standard set,
useful for development, debugging, or high-reliability environments.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from stageflow.pipeline.interceptors import BaseInterceptor
from stageflow.stages.context import PipelineContext
from stageflow.stages.result import StageResult

logger = logging.getLogger("stageflow.hardening")


class ImmutabilityInterceptor(BaseInterceptor):
    """Ensures ContextSnapshot and its nested structures are not mutated by stages.

    Since ContextSnapshot is frozen but may contain mutable containers (lists/dicts),
    this interceptor serializes the snapshot before and after stage execution
    to verify deep immutability.

    Performance Warning: This is expensive (double serialization per stage).
    Use primarily during development or testing.
    """

    name: str = "immutability_check"
    priority: int = 10  # Run early (before) and late (after)

    def __init__(self, crash_on_violation: bool = True) -> None:
        self.crash_on_violation = crash_on_violation
        self._snapshots: dict[str, str] = {}

    def _serialize_snapshot(self, ctx: PipelineContext) -> str | None:
        snapshot = getattr(ctx, "snapshot", None)
        if snapshot is None:
            return None
        serializer = getattr(snapshot, "to_dict", None)
        payload = serializer() if callable(serializer) else snapshot
        try:
            return json.dumps(payload, sort_keys=True, default=str)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Immutability check serialization failed",
                extra={"stage": getattr(ctx, "stage_name", "unknown"), "error": str(exc)},
            )
            return None

    async def before(self, stage_name: str, ctx: PipelineContext) -> None:
        # Capture pre-execution state
        snapshot_json = self._serialize_snapshot(ctx)
        if snapshot_json is None:
            logger.debug(
                "ImmutabilityInterceptor: snapshot missing; skipping pre-state",
                extra={"stage": stage_name},
            )
            return
        self._snapshots[stage_name] = snapshot_json

    async def after(self, stage_name: str, _result: StageResult, ctx: PipelineContext) -> None:
        if stage_name not in self._snapshots:
            return

        try:
            pre_json = self._snapshots.pop(stage_name)
            post_json = self._serialize_snapshot(ctx)
            if post_json is None:
                logger.debug(
                    "ImmutabilityInterceptor: snapshot missing post-stage; skipping",
                    extra={"stage": stage_name},
                )
                return

            if pre_json != post_json:
                msg = f"Immutability violation: Stage '{stage_name}' mutated the input ContextSnapshot."
                if self.crash_on_violation:
                    raise RuntimeError(msg)
                logger.error(msg)

        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            logger.warning(f"Immutability check failed for {stage_name}: {e}")


class ContextSizeInterceptor(BaseInterceptor):
    """Monitors the size of the context payload and warns on growth/thresholds.

    Leverages the compression utilities to estimate size and delta.
    """

    name: str = "context_size"
    priority: int = 42  # Run around metrics/logging time

    def __init__(
        self,
        max_size_bytes: int = 1024 * 1024,  # 1MB warning threshold
        warn_on_growth_bytes: int = 100 * 1024,  # Warn if single stage adds >100KB
    ) -> None:
        self.max_size_bytes = max_size_bytes
        self.warn_on_growth_bytes = warn_on_growth_bytes
        self._sizes: dict[str, int] = {}

    async def before(self, stage_name: str, ctx: PipelineContext) -> None:
        try:
            # Estimate size of snapshot + ephemeral data
            size = self._estimate_size(ctx)
            self._sizes[stage_name] = size

            if size > self.max_size_bytes:
                logger.warning(
                    f"Context size warning: {size / 1024:.1f}KB exceeds limit {self.max_size_bytes / 1024:.1f}KB "
                    f"before stage '{stage_name}'"
                )
        except Exception:
            pass

    async def after(self, stage_name: str, _result: StageResult, ctx: PipelineContext) -> None:
        if stage_name not in self._sizes:
            return

        try:
            prev_size = self._sizes.pop(stage_name)
            new_size = self._estimate_size(ctx)
            growth = new_size - prev_size

            if growth > self.warn_on_growth_bytes:
                logger.warning(
                    f"Significant context growth: Stage '{stage_name}' added {growth / 1024:.1f}KB "
                    f"(Total: {new_size / 1024:.1f}KB)"
                )

            # Emit metric via context if possible (optional integration)
            if hasattr(ctx, "record_metric"):
                ctx.record_metric("context_size_bytes", new_size, {"stage": stage_name})

        except Exception:
            pass

    def _estimate_size(self, ctx: PipelineContext) -> int:
        # Rough estimation using JSON dump of snapshot and data
        # We use the internal compression helper if useful, or just len(json)
        # Re-using _estimate_bytes from compression module would be ideal if exposed publicly
        # but here we do a quick check
        snapshot_payload: Any = {}
        snapshot = getattr(ctx, "snapshot", None)
        if snapshot is not None:
            serializer = getattr(snapshot, "to_dict", None)
            snapshot_payload = serializer() if callable(serializer) else snapshot

        data_payload = getattr(ctx, "data", None)
        if data_payload is None:
            data_payload = {}

        snapshot_size = len(json.dumps(snapshot_payload, default=str))
        data_size = len(json.dumps(data_payload, default=str))
        return snapshot_size + data_size
