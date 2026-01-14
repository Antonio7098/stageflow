"""Pipeline execution and logging utilities.

This module provides standardized utilities for running pipelines
with consistent logging, event capture, and result handling.

Usage:
    from stageflow.helpers import PipelineRunner, ObservableEventSink, setup_logging

    # Set up logging
    setup_logging(verbose=True)

    # Create runner with observability
    runner = PipelineRunner()

    # Run a pipeline
    result = await runner.run(
        pipeline=my_pipeline,
        input_text="Hello, world!",
        execution_mode="practice",
    )

    if result.success:
        print(f"Completed in {result.duration_ms}ms")
    else:
        print(f"Failed: {result.error}")
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from stageflow.context import ContextSnapshot
from stageflow.context.identity import RunIdentity
from stageflow.core import PipelineTimer, StageContext, StageOutput
from stageflow.events import set_event_sink
from stageflow.pipeline.dag import UnifiedPipelineCancelled, UnifiedStageGraph


def setup_logging(
    *,
    verbose: bool = False,
    json_format: bool = False,
    log_file: str | None = None,
) -> None:
    """Configure logging for pipeline execution.

    Sets up structured logging with appropriate formatters and handlers.

    Args:
        verbose: Enable DEBUG level logging.
        json_format: Use JSON-structured log format.
        log_file: Optional file path for log output.

    Example:
        setup_logging(verbose=True)
        setup_logging(json_format=True, log_file="pipeline.log")
    """
    level = logging.DEBUG if verbose else logging.INFO

    if json_format:
        formatter = JsonLogFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Reduce noise from some loggers
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


class JsonLogFormatter(logging.Formatter):
    """JSON-structured log formatter.

    Produces JSON lines for easy parsing by log aggregators.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include extra fields
        if hasattr(record, "event"):
            log_data["event"] = record.event
        if hasattr(record, "stage"):
            log_data["stage"] = record.stage
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms

        # Include exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


class ObservableEventSink:
    """Event sink that captures events for observability.

    Provides real-time event output with formatting, plus event capture
    for post-run analysis.

    Example:
        sink = ObservableEventSink(verbose=True, colorize=True)
        set_event_sink(sink)

        # Run pipeline...

        # After run
        sink.print_summary()
        events = sink.events  # Access captured events
    """

    def __init__(
        self,
        *,
        verbose: bool = True,
        colorize: bool = True,
        capture: bool = True,
    ) -> None:
        """Initialize event sink.

        Args:
            verbose: Print events as they occur.
            colorize: Use ANSI colors in output.
            capture: Store events for later access.
        """
        self.verbose = verbose
        self.colorize = colorize
        self.capture = capture
        self.events: list[dict[str, Any]] = []
        self._start_time = datetime.now(UTC)

    def _elapsed_ms(self) -> float:
        """Get milliseconds since sink creation."""
        return (datetime.now(UTC) - self._start_time).total_seconds() * 1000

    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        """Emit an event asynchronously."""
        self._record_event(type, data)

    def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        """Emit an event synchronously (fire-and-forget)."""
        self._record_event(type, data)

    def _record_event(self, event_type: str, data: dict[str, Any] | None) -> None:
        """Record and optionally print an event."""
        event = {
            "type": event_type,
            "data": data or {},
            "timestamp": datetime.now(UTC).isoformat(),
            "elapsed_ms": self._elapsed_ms(),
        }

        if self.capture:
            self.events.append(event)

        if self.verbose:
            self._print_event(event)

    def _print_event(self, event: dict[str, Any]) -> None:
        """Print event with formatting."""
        elapsed = event["elapsed_ms"]
        event_type = event["type"]

        # Color coding based on event type
        if self.colorize:
            if "error" in event_type or "failed" in event_type:
                color = "\033[91m"  # Red
            elif "completed" in event_type or "success" in event_type:
                color = "\033[92m"  # Green
            elif "started" in event_type:
                color = "\033[94m"  # Blue
            elif "tool" in event_type:
                color = "\033[93m"  # Yellow
            elif "skip" in event_type:
                color = "\033[90m"  # Gray
            else:
                color = "\033[96m"  # Cyan
            reset = "\033[0m"
        else:
            color = reset = ""

        print(f"{color}[{elapsed:8.2f}ms] {event_type}{reset}")

        # Print relevant data
        data = event.get("data", {})
        if data:
            relevant_keys = [
                "stage", "action_type", "tool_name", "error", "result",
                "duration_ms", "execution_mode", "behavior", "reason",
            ]
            for key in relevant_keys:
                if key in data:
                    value = data[key]
                    if isinstance(value, str) and len(value) > 80:
                        value = value[:80] + "..."
                    print(f"           {key}: {value}")

    def print_summary(self) -> None:
        """Print summary of captured events."""
        if not self.events:
            print("\nNo events captured.")
            return

        print("\n" + "=" * 60)
        print("EVENT SUMMARY")
        print("=" * 60)
        print(f"Total events: {len(self.events)}")
        print(f"Total time: {self._elapsed_ms():.1f}ms")

        # Group by type prefix
        by_prefix: dict[str, int] = {}
        for event in self.events:
            prefix = event["type"].split(".")[0]
            by_prefix[prefix] = by_prefix.get(prefix, 0) + 1

        print("\nBy category:")
        for prefix, count in sorted(by_prefix.items()):
            print(f"  {prefix}: {count}")

        # Show timeline (last 10 events)
        print("\nRecent events:")
        for event in self.events[-10:]:
            elapsed = event["elapsed_ms"]
            event_type = event["type"]
            print(f"  [{elapsed:8.2f}ms] {event_type}")

    def clear(self) -> None:
        """Clear captured events."""
        self.events.clear()
        self._start_time = datetime.now(UTC)

    def get_events_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """Get events matching a type pattern."""
        return [e for e in self.events if event_type in e["type"]]

    def get_stage_events(self, stage_name: str) -> list[dict[str, Any]]:
        """Get events for a specific stage."""
        return [
            e for e in self.events
            if e.get("data", {}).get("stage") == stage_name
            or stage_name in e["type"]
        ]


@dataclass
class RunResult:
    """Result of a pipeline run.

    Attributes:
        success: Whether the pipeline completed successfully.
        stages: Dict of stage name to output data.
        duration_ms: Total execution time in milliseconds.
        error: Error message if failed.
        error_type: Exception type name if failed.
        cancelled: Whether pipeline was cancelled by a stage.
        cancel_reason: Reason for cancellation.
        events: Captured events from the run.
        pipeline_run_id: The pipeline run identifier.
    """

    success: bool
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    duration_ms: float = 0.0
    error: str | None = None
    error_type: str | None = None
    cancelled: bool = False
    cancel_reason: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    pipeline_run_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "success": self.success,
            "stages": self.stages,
            "duration_ms": self.duration_ms,
        }
        if self.error:
            result["error"] = self.error
            result["error_type"] = self.error_type
        if self.cancelled:
            result["cancelled"] = self.cancelled
            result["cancel_reason"] = self.cancel_reason
        if self.pipeline_run_id:
            result["pipeline_run_id"] = str(self.pipeline_run_id)
        return result

    def get_stage_data(self, stage_name: str, key: str, default: Any = None) -> Any:
        """Get data from a specific stage's output."""
        stage_data = self.stages.get(stage_name, {})
        return stage_data.get(key, default)


class PipelineRunner:
    """Standardized pipeline execution with observability.

    Provides a consistent interface for running pipelines with:
    - Automatic event sink setup
    - Context creation from inputs
    - Error handling and result normalization
    - Timing and metrics capture

    Example:
        runner = PipelineRunner(colorize=True)

        result = await runner.run(
            pipeline=my_pipeline,
            input_text="Hello!",
            user_id=uuid4(),
        )

        print(f"Success: {result.success}")
        print(f"Duration: {result.duration_ms}ms")
    """

    def __init__(
        self,
        *,
        verbose: bool = True,
        colorize: bool = True,
        capture_events: bool = True,
    ) -> None:
        """Initialize runner.

        Args:
            verbose: Print events during execution.
            colorize: Use ANSI colors in output.
            capture_events: Capture events for post-run analysis.
        """
        self._verbose = verbose
        self._colorize = colorize
        self._capture_events = capture_events

    def create_snapshot(
        self,
        *,
        input_text: str | None = None,
        execution_mode: str = "practice",
        topology: str = "pipeline",
        pipeline_run_id: UUID | None = None,
        request_id: UUID | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        org_id: UUID | None = None,
        interaction_id: UUID | None = None,
        channel: str = "cli",
        **kwargs: Any,
    ) -> ContextSnapshot:
        """Create a ContextSnapshot with sensible defaults.

        Args:
            input_text: User input text.
            execution_mode: Pipeline execution mode.
            topology: Pipeline topology name.
            pipeline_run_id: Pipeline run ID (default: new UUID).
            request_id: Request ID (default: new UUID).
            session_id: Session ID (default: new UUID).
            user_id: User ID (default: new UUID).
            org_id: Organization ID.
            interaction_id: Interaction ID (default: new UUID).
            channel: Channel identifier.
            **kwargs: Additional ContextSnapshot fields.

        Returns:
            ContextSnapshot ready for pipeline execution.
        """
        run_id = RunIdentity(
            pipeline_run_id=pipeline_run_id or uuid4(),
            request_id=request_id or uuid4(),
            session_id=session_id or uuid4(),
            user_id=user_id or uuid4(),
            org_id=org_id,
            interaction_id=interaction_id or uuid4(),
        )

        return ContextSnapshot(
            run_id=run_id,
            topology=topology,
            execution_mode=execution_mode,
            input_text=input_text,
            metadata={"channel": channel},
            **kwargs,
        )

    async def run(
        self,
        pipeline: Any,  # Pipeline or UnifiedStageGraph
        *,
        input_text: str | None = None,
        execution_mode: str = "practice",
        snapshot: ContextSnapshot | None = None,
        config: dict[str, Any] | None = None,
        **snapshot_kwargs: Any,
    ) -> RunResult:
        """Run a pipeline and return results.

        Args:
            pipeline: Pipeline to run (Pipeline instance or UnifiedStageGraph).
            input_text: User input text.
            execution_mode: Pipeline execution mode.
            snapshot: Pre-built snapshot (if None, creates one).
            config: Additional stage context config.
            **snapshot_kwargs: Additional snapshot creation args.

        Returns:
            RunResult with execution status and data.
        """
        start_time = datetime.now(UTC)

        # Create event sink
        event_sink = ObservableEventSink(
            verbose=self._verbose,
            colorize=self._colorize,
            capture=self._capture_events,
        )
        set_event_sink(event_sink)

        # Create or use snapshot
        if snapshot is None:
            snapshot = self.create_snapshot(
                input_text=input_text,
                execution_mode=execution_mode,
                **snapshot_kwargs,
            )

        # Build graph if needed
        # Build graph if needed
        if hasattr(pipeline, "build"):
            graph = pipeline.build()
        elif isinstance(pipeline, UnifiedStageGraph):
            graph = pipeline
        else:
            graph = UnifiedStageGraph(specs=pipeline)

        from stageflow.stages.inputs import create_stage_inputs

        root_inputs = create_stage_inputs(
            snapshot=snapshot,
            prior_outputs={},
            ports=None,
            declared_deps=(),
            stage_name="__pipeline_root__",
        )

        stage_ctx = StageContext(
            snapshot=snapshot,
            inputs=root_inputs,
            stage_name="__pipeline_root__",
            timer=PipelineTimer(),
            event_sink=event_sink,
        )

        # Print header
        if self._verbose:
            print("\n" + "=" * 60)
            print(f"RUNNING PIPELINE: {snapshot.topology}")
            print("=" * 60)
            if input_text:
                display_text = input_text[:60] + "..." if len(input_text) > 60 else input_text
                print(f"Input: {display_text}")
            print(f"Mode: {execution_mode}")
            print("-" * 60)

        # Run pipeline - graph.run() takes snapshot and event_sink
        try:
            results = await graph.run(stage_ctx)
            duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return RunResult(
                success=True,
                stages={name: output.data for name, output in results.items()},
                duration_ms=duration_ms,
                events=event_sink.events if self._capture_events else [],
                pipeline_run_id=snapshot.pipeline_run_id,
            )

        except UnifiedPipelineCancelled as e:
            duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return RunResult(
                success=True,
                stages={name: output.data for name, output in e.results.items()},
                duration_ms=duration_ms,
                cancelled=True,
                cancel_reason=e.reason,
                events=event_sink.events if self._capture_events else [],
                pipeline_run_id=snapshot.pipeline_run_id,
            )

        except Exception as e:
            duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return RunResult(
                success=False,
                duration_ms=duration_ms,
                error=str(e),
                error_type=type(e).__name__,
                events=event_sink.events if self._capture_events else [],
                pipeline_run_id=snapshot.pipeline_run_id,
            )

    def print_result(self, result: RunResult, *, show_data: bool = True) -> None:
        """Print a formatted result summary.

        Args:
            result: The RunResult to print.
            show_data: Whether to show stage output data.
        """
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)

        if result.success:
            if self._colorize:
                print("\033[92mPipeline completed successfully!\033[0m")
            else:
                print("Pipeline completed successfully!")

            if result.cancelled:
                print(f"  (Cancelled: {result.cancel_reason})")

            print(f"  Duration: {result.duration_ms:.1f}ms")
            print(f"  Stages: {len(result.stages)}")

            if show_data:
                for stage_name, stage_data in result.stages.items():
                    print(f"\n  Stage: {stage_name}")
                    if isinstance(stage_data, dict):
                        for key, value in stage_data.items():
                            if isinstance(value, str) and len(value) > 100:
                                print(f"    {key}: {value[:100]}...")
                            else:
                                print(f"    {key}: {value}")
        else:
            if self._colorize:
                print(f"\033[91mPipeline failed: {result.error}\033[0m")
            else:
                print(f"Pipeline failed: {result.error}")
            print(f"  Error type: {result.error_type}")
            print(f"  Duration: {result.duration_ms:.1f}ms")


__all__ = [
    "JsonLogFormatter",
    "ObservableEventSink",
    "PipelineRunner",
    "RunResult",
    "setup_logging",
]
