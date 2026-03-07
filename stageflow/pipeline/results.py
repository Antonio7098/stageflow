"""Convenience wrapper for pipeline execution results."""

from __future__ import annotations

from stageflow.core import StageOutput, StageStatus


class PipelineResults(dict[str, StageOutput]):
    """Dict-like stage results with ergonomic helper methods."""

    def require(self, stage_name: str) -> StageOutput:
        """Return a stage output or raise a helpful KeyError."""
        try:
            return self[stage_name]
        except KeyError as exc:
            available = ", ".join(sorted(self.keys())) or "<none>"
            raise KeyError(
                f"Stage {stage_name!r} not found in pipeline results. Available: {available}"
            ) from exc

    def output(self, stage_name: str, default: StageOutput | None = None) -> StageOutput | None:
        """Return a stage output if present."""
        return self.get(stage_name, default)

    def require_ok(self, stage_name: str) -> StageOutput:
        """Return a stage output only when it finished with OK status."""
        output = self.require(stage_name)
        if output.status != StageStatus.OK:
            detail = output.error or output.data.get("reason") or output.data.get("cancel_reason")
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(
                f"Stage {stage_name!r} did not complete with OK status "
                f"({output.status.value}){suffix}"
            )
        return output

    def data(self, stage_name: str, default: dict | None = None) -> dict:
        """Return the `.data` payload for a stage."""
        output = self.get(stage_name)
        if output is None:
            if default is not None:
                return default
            raise KeyError(stage_name)
        return output.data

    def ok(self, stage_name: str) -> bool:
        """Return True when the stage finished successfully."""
        output = self.get(stage_name)
        return output is not None and output.status == StageStatus.OK

    def failed(self) -> list[str]:
        """Return the names of failed stages."""
        return [name for name, output in self.items() if output.status == StageStatus.FAIL]


__all__ = ["PipelineResults"]
