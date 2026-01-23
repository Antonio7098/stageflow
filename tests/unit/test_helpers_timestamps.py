from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from stageflow.helpers.timestamps import detect_unix_precision, normalize_to_utc, parse_timestamp


class TestDetectUnixPrecision:
    def test_detects_seconds_milliseconds_microseconds(self):
        assert detect_unix_precision(1_706_000_000) == "seconds"
        assert detect_unix_precision(1_706_000_000_123) == "milliseconds"
        assert detect_unix_precision(1_706_000_000_123_456) == "microseconds"

    def test_rejects_nanosecond_precision(self):
        with pytest.raises(ValueError):
            detect_unix_precision(1_706_000_000_123_456_789)


class TestParseTimestamp:
    def test_parses_numeric_seconds(self):
        ts = 1_700_000_000
        result = parse_timestamp(ts)
        assert result == datetime.fromtimestamp(ts, tz=UTC)

    def test_parses_numeric_string_with_precision(self):
        ms = 1_700_000_000_500
        as_str = str(ms)
        result = parse_timestamp(as_str)
        assert result == datetime.fromtimestamp(ms / 1_000, tz=UTC)

    def test_parses_microseconds(self):
        us = 1_700_000_000_123_456
        result = parse_timestamp(us)
        assert result == datetime.fromtimestamp(us / 1_000_000, tz=UTC)

    def test_parses_rfc_2822(self):
        value = "Thu, 05 Oct 2023 14:48:00 GMT"
        result = parse_timestamp(value)
        assert result == datetime(2023, 10, 5, 14, 48, tzinfo=UTC)

    def test_parses_iso_8601_zulu(self):
        value = "2023-10-05T14:48:00Z"
        result = parse_timestamp(value)
        assert result == datetime(2023, 10, 5, 14, 48, tzinfo=UTC)

    def test_parses_human_readable_with_default_timezone(self):
        value = "October 5, 2023"
        default_tz = timezone(timedelta(hours=-4))
        result = parse_timestamp(value, default_timezone=default_tz)
        expected = datetime(2023, 10, 5, tzinfo=default_tz).astimezone(UTC)
        assert result == expected

    def test_rejects_unknown_format(self):
        with pytest.raises(ValueError):
            parse_timestamp("not a timestamp")

    def test_type_checking(self):
        with pytest.raises(TypeError):
            parse_timestamp({})  # type: ignore[arg-type]


class TestNormalizeToUtc:
    def test_applies_default_timezone(self):
        naive = datetime(2023, 10, 5, 14, 48)
        default_tz = timezone(timedelta(hours=2))
        normalized = normalize_to_utc(naive, default_timezone=default_tz)
        assert normalized == datetime(2023, 10, 5, 12, 48, tzinfo=UTC)

    def test_preserves_timezone_when_default_none(self):
        aware = datetime(2023, 10, 5, 14, 48, tzinfo=timezone(timedelta(hours=-5)))
        normalized = normalize_to_utc(aware, default_timezone=None)
        assert normalized.utcoffset() == timedelta(hours=-5)
