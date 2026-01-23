"""Timestamp parsing utilities for Stageflow pipelines.

This module consolidates all timestamp normalization logic required by the
TRANSFORM tester fixes:

1. Detect Unix timestamp precision (seconds/milliseconds/microseconds)
   before calling :func:`datetime.fromtimestamp` to avoid overflow errors.
2. Parse RFC 2822 timestamps explicitly via
   :func:`email.utils.parsedate_to_datetime` to support email/HTTP headers.
3. Provide :func:`parse_timestamp` as a DX convenience that accepts raw
   strings or numbers, normalizes to UTC, and handles common human readable
   formats in addition to ISO 8601 and Unix epochs.

All parsing paths return timezone-aware datetimes in UTC by default to keep
pipeline telemetry consistent.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, tzinfo
from email.utils import parsedate_to_datetime
from typing import Literal

UnixPrecision = Literal["seconds", "milliseconds", "microseconds"]


# Minimal set of human friendly formats we observed in tester payloads
_HUMAN_READABLE_FORMATS: Iterable[str] = (
    "%B %d, %Y",  # October 5, 2023
    "%b %d, %Y",  # Oct 5, 2023
    "%d %B %Y",  # 05 October 2023
    "%d %b %Y",  # 05 Oct 2023
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)


def detect_unix_precision(timestamp: int | float) -> UnixPrecision:
    """Detect the precision of a Unix timestamp by digit count.

    Args:
        timestamp: Raw epoch value in seconds/milliseconds/microseconds.

    Returns:
        Literal precision label used for downstream scaling.

    Raises:
        ValueError: If the timestamp has more than 16 digits (nanoseconds
        or beyond) which Stageflow does not support.
    """

    integer_part = int(abs(float(timestamp)))
    digits = len(str(integer_part)) if integer_part != 0 else 1

    if digits <= 10:
        return "seconds"
    if digits <= 13:
        return "milliseconds"
    if digits <= 16:
        return "microseconds"

    raise ValueError(f"Unsupported Unix timestamp precision for {timestamp!r}")


def normalize_to_utc(dt: datetime, *, default_timezone: tzinfo | None = UTC) -> datetime:
    """Normalize a datetime to UTC, applying a default timezone if naive."""

    if dt.tzinfo is None:
        if default_timezone is None:
            return dt
        dt = dt.replace(tzinfo=default_timezone)

    if default_timezone is None:
        return dt

    return dt.astimezone(UTC)


def parse_timestamp(value: str | int | float, *, default_timezone: tzinfo | None = UTC) -> datetime:
    """Parse a timestamp string/number into a timezone-aware UTC datetime.

    Args:
        value: Timestamp as string/number (ISO 8601, RFC 2822, Unix epoch,
            or select human readable formats).
        default_timezone: Applied when parsing timestamps that do not include
            explicit timezone information.

    Raises:
        TypeError: When ``value`` is not a string/number.
        ValueError: When the format cannot be detected.
    """

    if not isinstance(value, (str, int, float)):
        raise TypeError(f"Unsupported timestamp input type: {type(value).__name__}")

    if isinstance(value, (int, float)):
        return _parse_unix_timestamp(value)

    text = value.strip()
    if not text:
        raise ValueError("Timestamp string cannot be empty")

    # Numeric string (seconds, milliseconds, microseconds)
    try:
        number = int(text)
    except ValueError:
        try:
            number = float(text)
        except ValueError:
            number = None
    if number is not None:
        return _parse_unix_timestamp(number)

    # RFC 2822 (e.g., Thu, 05 Oct 2023 14:48:00 GMT)
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        parsed = None
    if parsed is not None:
        return normalize_to_utc(parsed, default_timezone=default_timezone)

    iso_candidate = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        return normalize_to_utc(parsed, default_timezone=default_timezone)
    except ValueError:
        pass

    for fmt in _HUMAN_READABLE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return normalize_to_utc(parsed, default_timezone=default_timezone)

    raise ValueError(f"Unsupported timestamp format: {value!r}")


def _parse_unix_timestamp(value: int | float) -> datetime:
    if isinstance(value, float) and not value.is_integer():
        seconds = float(value)
    else:
        precision = detect_unix_precision(value)
        if precision == "seconds":
            divisor = 1
        elif precision == "milliseconds":
            divisor = 1_000
        else:
            divisor = 1_000_000
        seconds = int(value) / divisor

    return datetime.fromtimestamp(seconds, tz=UTC)


__all__ = ["parse_timestamp", "detect_unix_precision", "normalize_to_utc"]
