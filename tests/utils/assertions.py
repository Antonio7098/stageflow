"""Custom assertions for stageflow tests."""

from __future__ import annotations

from typing import Any

from tests.utils.mocks import MockEventSink


def assert_event_emitted(
    sink: MockEventSink,
    event_type: str,
    *,
    data_contains: dict[str, Any] | None = None,
    count: int | None = None,
) -> None:
    """Assert that an event of the given type was emitted.

    Args:
        sink: The mock event sink to check
        event_type: The event type to look for
        data_contains: Optional dict of key-value pairs that must be in event data
        count: If provided, assert exactly this many events of this type

    Raises:
        AssertionError: If assertion fails
    """
    events = sink.get_events_by_type(event_type)

    if count is not None:
        assert len(events) == count, (
            f"Expected {count} events of type '{event_type}', got {len(events)}"
        )
    else:
        assert len(events) > 0, f"No events of type '{event_type}' were emitted"

    if data_contains:
        for event in events:
            event_data = event.get("data", {}) or {}
            for key, value in data_contains.items():
                assert key in event_data, (
                    f"Event '{event_type}' missing key '{key}' in data"
                )
                assert event_data[key] == value, (
                    f"Event '{event_type}' key '{key}' expected {value}, got {event_data[key]}"
                )


def assert_stage_completed(
    sink: MockEventSink,
    stage_name: str,
    *,
    check_started: bool = True,
) -> None:
    """Assert that a stage completed successfully.

    Args:
        sink: The mock event sink to check
        stage_name: Name of the stage
        check_started: Also verify started event was emitted

    Raises:
        AssertionError: If assertion fails
    """
    if check_started:
        assert sink.has_event(f"stage.{stage_name}.started"), (
            f"Stage '{stage_name}' did not emit started event"
        )

    assert sink.has_event(f"stage.{stage_name}.completed"), (
        f"Stage '{stage_name}' did not emit completed event"
    )


def assert_stage_failed(
    sink: MockEventSink,
    stage_name: str,
    *,
    error_contains: str | None = None,
) -> None:
    """Assert that a stage failed.

    Args:
        sink: The mock event sink to check
        stage_name: Name of the stage
        error_contains: If provided, check error message contains this string

    Raises:
        AssertionError: If assertion fails
    """
    events = sink.get_events_by_type(f"stage.{stage_name}.failed")
    assert len(events) > 0, f"Stage '{stage_name}' did not emit failed event"

    if error_contains:
        event_data = events[0].get("data", {}) or {}
        error_msg = event_data.get("error", "") or event_data.get("error_message", "")
        assert error_contains in error_msg, (
            f"Expected error containing '{error_contains}', got '{error_msg}'"
        )


__all__ = [
    "assert_event_emitted",
    "assert_stage_completed",
    "assert_stage_failed",
]
