#!/usr/bin/env python3
"""CLI script to run pipelines with full observability.

Usage:
    python run_pipeline.py unified_tools "echo transform validate"
    python run_pipeline.py observability_demo "hello world this is a test"
    python run_pipeline.py unified_tools "restricted action" --mode doc_edit
    python run_pipeline.py unified_tools "restricted action" --mode roleplay
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, UTC
from typing import Any
from uuid import uuid4

# Add parent to path for imports
sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from stageflow import StageContext, set_event_sink, LoggingEventSink
from stageflow.context import ContextSnapshot
from stageflow.pipeline.dag import UnifiedStageGraph, UnifiedPipelineCancelled


class ObservableEventSink:
    """Event sink that prints events with formatting for observability."""
    
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.events: list[dict[str, Any]] = []
        self._start_time = datetime.now(UTC)
    
    def _elapsed_ms(self) -> float:
        return (datetime.now(UTC) - self._start_time).total_seconds() * 1000
    
    async def emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        """Emit an event asynchronously."""
        event = {
            "type": type,
            "data": data or {},
            "timestamp": datetime.now(UTC).isoformat(),
            "elapsed_ms": self._elapsed_ms(),
        }
        self.events.append(event)
        
        if self.verbose:
            self._print_event(event)
    
    def try_emit(self, *, type: str, data: dict[str, Any] | None) -> None:
        """Emit an event synchronously (fire-and-forget)."""
        event = {
            "type": type,
            "data": data or {},
            "timestamp": datetime.now(UTC).isoformat(),
            "elapsed_ms": self._elapsed_ms(),
        }
        self.events.append(event)
        
        if self.verbose:
            self._print_event(event)
    
    def _print_event(self, event: dict[str, Any]) -> None:
        """Print event with formatting."""
        elapsed = event["elapsed_ms"]
        event_type = event["type"]
        
        # Color coding based on event type
        if "error" in event_type or "failed" in event_type:
            color = "\033[91m"  # Red
        elif "completed" in event_type or "success" in event_type:
            color = "\033[92m"  # Green
        elif "started" in event_type:
            color = "\033[94m"  # Blue
        elif "tool" in event_type:
            color = "\033[93m"  # Yellow
        else:
            color = "\033[96m"  # Cyan
        
        reset = "\033[0m"
        
        print(f"{color}[{elapsed:8.2f}ms] {event_type}{reset}")
        
        # Print relevant data
        data = event.get("data", {})
        if data:
            relevant_keys = ["stage", "action_type", "tool_name", "error", "result", 
                           "duration_ms", "execution_mode", "behavior"]
            for key in relevant_keys:
                if key in data:
                    print(f"           {key}: {data[key]}")
    
    def print_summary(self) -> None:
        """Print summary of all events."""
        print("\n" + "=" * 60)
        print("EVENT SUMMARY")
        print("=" * 60)
        print(f"Total events: {len(self.events)}")
        
        # Group by type prefix
        by_prefix: dict[str, int] = {}
        for event in self.events:
            prefix = event["type"].split(".")[0]
            by_prefix[prefix] = by_prefix.get(prefix, 0) + 1
        
        print("\nBy category:")
        for prefix, count in sorted(by_prefix.items()):
            print(f"  {prefix}: {count}")
        
        # Show timeline
        print("\nTimeline:")
        for event in self.events:
            elapsed = event["elapsed_ms"]
            event_type = event["type"]
            print(f"  [{elapsed:8.2f}ms] {event_type}")


def setup_logging(verbose: bool) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    
    # Reduce noise from some loggers
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def create_context_snapshot(
    input_text: str,
    execution_mode: str,
) -> ContextSnapshot:
    """Create a ContextSnapshot for pipeline execution."""
    return ContextSnapshot(
        pipeline_run_id=uuid4(),
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        org_id=uuid4(),
        interaction_id=uuid4(),
        topology="test_pipeline",
        channel="cli",
        execution_mode=execution_mode,
        input_text=input_text,
    )


async def run_unified_tools_pipeline(
    input_text: str,
    execution_mode: str,
    event_sink: ObservableEventSink,
) -> dict[str, Any]:
    """Run the unified tools pipeline."""
    from test_app.pipelines.unified_tools import create_unified_tools_pipeline
    
    specs = create_unified_tools_pipeline()
    graph = UnifiedStageGraph(specs)
    
    snapshot = create_context_snapshot(input_text, execution_mode)
    ctx = StageContext(
        snapshot=snapshot,
        config={"event_sink": event_sink},
    )
    
    print("\n" + "=" * 60)
    print("RUNNING: unified_tools pipeline")
    print("=" * 60)
    print(f"Input: {input_text}")
    print(f"Execution Mode: {execution_mode}")
    print("-" * 60)
    
    try:
        results = await graph.run(ctx)
        return {
            "success": True,
            "stages": {name: output.data for name, output in results.items()},
        }
    except UnifiedPipelineCancelled as e:
        return {
            "success": True,
            "cancelled": True,
            "reason": e.reason,
            "stages": {name: output.data for name, output in e.results.items()},
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }


async def run_observability_demo_pipeline(
    input_text: str,
    execution_mode: str,
    event_sink: ObservableEventSink,
) -> dict[str, Any]:
    """Run the observability demo pipeline."""
    from test_app.pipelines.observability_demo import create_observability_demo_pipeline
    
    specs = create_observability_demo_pipeline()
    graph = UnifiedStageGraph(specs)
    
    snapshot = create_context_snapshot(input_text, execution_mode)
    ctx = StageContext(
        snapshot=snapshot,
        config={"event_sink": event_sink},
    )
    
    print("\n" + "=" * 60)
    print("RUNNING: observability_demo pipeline")
    print("=" * 60)
    print(f"Input: {input_text}")
    print(f"Execution Mode: {execution_mode}")
    print("-" * 60)
    
    try:
        results = await graph.run(ctx)
        return {
            "success": True,
            "stages": {name: output.data for name, output in results.items()},
        }
    except UnifiedPipelineCancelled as e:
        return {
            "success": True,
            "cancelled": True,
            "reason": e.reason,
            "stages": {name: output.data for name, output in e.results.items()},
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }


async def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run stageflow pipelines with full observability",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py unified_tools "echo transform"
  python run_pipeline.py observability_demo "hello world test"
  python run_pipeline.py unified_tools "restricted" --mode doc_edit
  python run_pipeline.py unified_tools "restricted" --mode roleplay
        """,
    )
    parser.add_argument(
        "pipeline",
        choices=["unified_tools", "observability_demo"],
        help="Pipeline to run",
    )
    parser.add_argument(
        "input",
        help="Input text for the pipeline",
    )
    parser.add_argument(
        "--mode", "-m",
        default="practice",
        help="Execution mode (default: practice)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--no-events",
        action="store_true",
        help="Suppress event output",
    )
    
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    
    # Create observable event sink
    event_sink = ObservableEventSink(verbose=not args.no_events)
    set_event_sink(event_sink)
    
    # Run the selected pipeline
    if args.pipeline == "unified_tools":
        result = await run_unified_tools_pipeline(
            args.input,
            args.mode,
            event_sink,
        )
    elif args.pipeline == "observability_demo":
        result = await run_observability_demo_pipeline(
            args.input,
            args.mode,
            event_sink,
        )
    else:
        print(f"Unknown pipeline: {args.pipeline}", file=sys.stderr)
        return 1
    
    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if result.get("success"):
            print("\033[92mPipeline completed successfully!\033[0m")
            
            if result.get("cancelled"):
                print(f"  (Cancelled: {result.get('reason')})")
            
            stages = result.get("stages", {})
            for stage_name, stage_data in stages.items():
                print(f"\n  Stage: {stage_name}")
                if isinstance(stage_data, dict):
                    for key, value in stage_data.items():
                        if isinstance(value, str) and len(value) > 100:
                            print(f"    {key}: {value[:100]}...")
                        else:
                            print(f"    {key}: {value}")
        else:
            print(f"\033[91mPipeline failed: {result.get('error')}\033[0m")
            print(f"  Error type: {result.get('error_type')}")
    
    # Print event summary
    if not args.no_events:
        event_sink.print_summary()
    
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
