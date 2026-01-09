"""Property-based tests for event sequencing.

These tests verify that:
- Event sequences are always monotonically increasing
- No duplicate sequence numbers in a run
- Sequence numbers start from 1
"""

from __future__ import annotations

from hypothesis import given, settings

from tests.property.strategies import event_sequences


class TestEventSequenceProperties:
    """Property tests for event sequences."""

    @given(event_sequences(min_events=2, max_events=20))
    @settings(max_examples=100)
    def test_sequence_is_monotonically_increasing(self, events: list[dict]) -> None:
        """Event sequences are always monotonically increasing."""
        for i in range(1, len(events)):
            prev_seq = events[i - 1]["sequence"]
            curr_seq = events[i]["sequence"]
            assert curr_seq > prev_seq, (
                f"Sequence not increasing: {prev_seq} -> {curr_seq}"
            )

    @given(event_sequences(min_events=1, max_events=20))
    @settings(max_examples=100)
    def test_no_duplicate_sequence_numbers(self, events: list[dict]) -> None:
        """No duplicate sequence numbers in a run."""
        sequences = [e["sequence"] for e in events]
        assert len(sequences) == len(set(sequences)), (
            "Duplicate sequence numbers found"
        )

    @given(event_sequences(min_events=1, max_events=20))
    @settings(max_examples=100)
    def test_sequence_starts_from_one(self, events: list[dict]) -> None:
        """Sequence numbers start from 1."""
        if events:
            assert events[0]["sequence"] == 1, (
                f"First sequence is {events[0]['sequence']}, expected 1"
            )

    @given(event_sequences(min_events=1, max_events=20))
    @settings(max_examples=100)
    def test_all_events_have_type(self, events: list[dict]) -> None:
        """All events have a type field."""
        for event in events:
            assert "type" in event, "Event missing type field"
            assert isinstance(event["type"], str), "Event type must be string"

    @given(event_sequences(min_events=1, max_events=20))
    @settings(max_examples=100)
    def test_all_events_have_timestamp(self, events: list[dict]) -> None:
        """All events have a timestamp field."""
        for event in events:
            assert "timestamp" in event, "Event missing timestamp field"
