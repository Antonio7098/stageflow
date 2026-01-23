"""Tests for ENRICH context utilities."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from stageflow.context.enrich import (
    ConflictDetector,
    ContextUtilization,
    TruncationTracker,
    VersionMetadata,
)


class TestContextUtilization:
    """Tests for ContextUtilization."""

    def test_initialization(self):
        """Test basic initialization."""
        util = ContextUtilization(max_tokens=4096)

        assert util.max_tokens == 4096
        assert util.used_tokens == 0
        assert util.available_tokens == 4096

    def test_with_reserved_tokens(self):
        """Test initialization with reserved tokens."""
        util = ContextUtilization(max_tokens=4096, reserved_tokens=512)

        assert util.available_tokens == 4096 - 512

    def test_utilization_calculation(self):
        """Test utilization percentage calculation."""
        util = ContextUtilization(max_tokens=100, used_tokens=75)

        assert util.utilization == 0.75

    def test_is_near_limit(self):
        """Test near-limit detection (>80%)."""
        util_low = ContextUtilization(max_tokens=100, used_tokens=70)
        util_high = ContextUtilization(max_tokens=100, used_tokens=85)

        assert not util_low.is_near_limit
        assert util_high.is_near_limit

    def test_is_at_limit(self):
        """Test at-limit detection."""
        util = ContextUtilization(max_tokens=100, used_tokens=100)

        assert util.is_at_limit

    def test_is_at_limit_with_reserved(self):
        """Test at-limit with reserved tokens."""
        util = ContextUtilization(max_tokens=100, used_tokens=80, reserved_tokens=20)

        assert util.is_at_limit

    def test_can_fit(self):
        """Test can_fit check."""
        util = ContextUtilization(max_tokens=100, used_tokens=80)

        assert util.can_fit(10)
        assert util.can_fit(20)
        assert not util.can_fit(25)

    def test_add_tokens(self):
        """Test adding tokens."""
        util = ContextUtilization(max_tokens=100)

        assert util.add(50)
        assert util.used_tokens == 50

        assert util.add(30)
        assert util.used_tokens == 80

        # Should fail when exceeding limit
        assert not util.add(30)
        assert util.used_tokens == 80  # Unchanged

    def test_to_dict(self):
        """Test dictionary serialization."""
        util = ContextUtilization(max_tokens=100, used_tokens=75, reserved_tokens=10)

        d = util.to_dict()

        assert d["max_tokens"] == 100
        assert d["used_tokens"] == 75
        assert d["reserved_tokens"] == 10
        assert d["available_tokens"] == 15
        assert d["utilization"] == 0.75


class TestTruncationTracker:
    """Tests for TruncationTracker."""

    def test_record_truncation(self):
        """Test recording a truncation event."""
        tracker = TruncationTracker()

        event = tracker.record_truncation(
            original_tokens=1000,
            truncated_tokens=500,
            strategy="tail",
            content_type="document",
            reason="context_limit",
        )

        assert event.original_tokens == 1000
        assert event.truncated_tokens == 500
        assert event.tokens_removed == 500
        assert event.preserved_ratio == 0.5

    def test_event_count(self):
        """Test event counting."""
        tracker = TruncationTracker()

        tracker.record_truncation(1000, 500, "tail", "document", "limit")
        tracker.record_truncation(800, 400, "head", "conversation", "limit")

        assert tracker.event_count == 2

    def test_total_tokens_removed(self):
        """Test total tokens removed calculation."""
        tracker = TruncationTracker()

        tracker.record_truncation(1000, 500, "tail", "document", "limit")
        tracker.record_truncation(800, 600, "head", "conversation", "limit")

        assert tracker.total_tokens_removed == 700  # 500 + 200

    def test_get_summary(self):
        """Test summary generation."""
        tracker = TruncationTracker()

        tracker.record_truncation(1000, 500, "tail", "document", "limit")
        tracker.record_truncation(800, 400, "semantic", "retrieval", "quality")

        summary = tracker.get_summary()

        assert summary["event_count"] == 2
        assert summary["total_tokens_removed"] == 900
        assert set(summary["strategies_used"]) == {"tail", "semantic"}
        assert set(summary["content_types"]) == {"document", "retrieval"}

    def test_empty_summary(self):
        """Test summary with no events."""
        tracker = TruncationTracker()

        summary = tracker.get_summary()

        assert summary["event_count"] == 0
        assert summary["total_tokens_removed"] == 0

    def test_event_emission(self):
        """Test event emission to sink."""
        mock_sink = MagicMock()
        mock_sink.try_emit = MagicMock()

        tracker = TruncationTracker(event_sink=mock_sink)

        tracker.record_truncation(1000, 500, "tail", "document", "limit")

        mock_sink.try_emit.assert_called_once()
        call_args = mock_sink.try_emit.call_args
        assert call_args[0][0] == "context.truncation"


class TestVersionMetadata:
    """Tests for VersionMetadata."""

    def test_create_basic(self):
        """Test basic creation."""
        meta = VersionMetadata.create(
            content_id="doc_123",
            version="v1.0",
            source="vector_db",
        )

        assert meta.content_id == "doc_123"
        assert meta.version == "v1.0"
        assert meta.source == "vector_db"
        assert meta.checksum is None

    def test_create_with_content_checksum(self):
        """Test creation with content for checksum."""
        meta = VersionMetadata.create(
            content_id="doc_123",
            version="v1.0",
            source="api",
            content="Hello, World!",
        )

        assert meta.checksum is not None
        assert len(meta.checksum) == 16

    def test_age_calculation(self):
        """Test age calculation."""
        meta = VersionMetadata(
            content_id="doc_123",
            version="v1.0",
            retrieved_at=datetime.now(UTC) - timedelta(seconds=60),
            source="api",
        )

        assert 59 <= meta.age_seconds <= 61

    def test_is_stale_without_ttl(self):
        """Test staleness without TTL."""
        meta = VersionMetadata(
            content_id="doc_123",
            version="v1.0",
            retrieved_at=datetime.now(UTC) - timedelta(hours=1),
            source="api",
            ttl_seconds=None,
        )

        assert not meta.is_stale

    def test_is_stale_within_ttl(self):
        """Test staleness within TTL."""
        meta = VersionMetadata(
            content_id="doc_123",
            version="v1.0",
            retrieved_at=datetime.now(UTC) - timedelta(seconds=30),
            source="api",
            ttl_seconds=60,
        )

        assert not meta.is_stale

    def test_is_stale_exceeded_ttl(self):
        """Test staleness when TTL exceeded."""
        meta = VersionMetadata(
            content_id="doc_123",
            version="v1.0",
            retrieved_at=datetime.now(UTC) - timedelta(seconds=120),
            source="api",
            ttl_seconds=60,
        )

        assert meta.is_stale

    def test_to_dict(self):
        """Test dictionary serialization."""
        meta = VersionMetadata.create(
            content_id="doc_123",
            version="v1.0",
            source="api",
            ttl_seconds=300,
            tags=["important", "cached"],
        )

        d = meta.to_dict()

        assert d["content_id"] == "doc_123"
        assert d["version"] == "v1.0"
        assert d["source"] == "api"
        assert d["ttl_seconds"] == 300
        assert d["tags"] == ["important", "cached"]
        assert "age_seconds" in d
        assert "is_stale" in d


class TestConflictDetector:
    """Tests for ConflictDetector."""

    def test_no_conflict_when_old_is_none(self):
        """Test no conflict when old value is None."""
        detector = ConflictDetector()

        result = detector.check_and_resolve("field", None, "new_value")

        assert not result.has_conflict
        assert result.new_value == "new_value"

    def test_no_conflict_when_equal(self):
        """Test no conflict when values are equal."""
        detector = ConflictDetector()

        result = detector.check_and_resolve("field", "same", "same")

        assert not result.has_conflict

    def test_conflict_keep_new_default(self):
        """Test conflict with default keep_new strategy."""
        detector = ConflictDetector(default_strategy="keep_new")

        result = detector.check_and_resolve("field", "old", "new")

        assert result.has_conflict
        assert result.resolution == "keep_new"
        assert result.merged_value == "new"

    def test_conflict_keep_old(self):
        """Test conflict with keep_old strategy."""
        detector = ConflictDetector(default_strategy="keep_old")

        result = detector.check_and_resolve("field", "old", "new")

        assert result.has_conflict
        assert result.resolution == "keep_old"
        assert result.merged_value == "old"

    def test_conflict_error_strategy(self):
        """Test conflict with error strategy."""
        detector = ConflictDetector(default_strategy="error")

        result = detector.check_and_resolve("field", "old", "new")

        assert result.has_conflict
        assert result.resolution == "error"
        assert result.merged_value is None

    def test_merge_lists(self):
        """Test merge strategy for lists."""
        detector = ConflictDetector(default_strategy="merge")

        result = detector.check_and_resolve(
            "tags",
            ["a", "b"],
            ["b", "c"],
        )

        assert result.has_conflict
        assert result.resolution == "merge"
        assert result.merged_value == ["a", "b", "c"]  # Deduplicated

    def test_merge_dicts(self):
        """Test merge strategy for dicts."""
        detector = ConflictDetector(default_strategy="merge")

        result = detector.check_and_resolve(
            "config",
            {"a": 1, "b": 2},
            {"b": 3, "c": 4},
        )

        assert result.has_conflict
        assert result.resolution == "merge"
        assert result.merged_value == {"a": 1, "b": 3, "c": 4}

    def test_merge_strings(self):
        """Test merge strategy for strings."""
        detector = ConflictDetector(default_strategy="merge")

        result = detector.check_and_resolve(
            "content",
            "First part",
            "Second part",
        )

        assert result.has_conflict
        assert result.resolution == "merge"
        assert result.merged_value == "First part\nSecond part"

    def test_per_field_strategy(self):
        """Test per-field strategy override."""
        detector = ConflictDetector(
            default_strategy="keep_new",
            merge_strategies={
                "protected_field": "keep_old",
            },
        )

        # Default field uses keep_new
        result1 = detector.check_and_resolve("normal_field", "old", "new")
        assert result1.merged_value == "new"

        # Protected field uses keep_old
        result2 = detector.check_and_resolve("protected_field", "old", "new")
        assert result2.merged_value == "old"
