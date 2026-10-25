from datetime import datetime, timedelta, timezone
import pytest

from dashboard.formatting import (
    CATEGORY_OPTIONS,
    PRIORITY_COLORS,
    STATUS_COLORS,
    format_datetime,
)


@pytest.fixture
def deterministic_timezone(monkeypatch):
    """Pin get_local_timezone to a fixed UTC+2 timezone (e.g. EET / UTC+02:00)."""
    fixed_tz = timezone(timedelta(hours=2))
    monkeypatch.setattr("dashboard.formatting.get_local_timezone", lambda: fixed_tz)
    return fixed_tz


def test_format_datetime_none():
    """Test None and empty inputs return '-'."""
    assert format_datetime(None) == "-"
    assert format_datetime("") == "-"
    assert format_datetime("   ") == "-"
    assert format_datetime("None") == "-"
    assert format_datetime("null") == "-"


def test_format_datetime_naive_utc_string(deterministic_timezone):
    """
    Test naive UTC string from API is treated as UTC and converted to local timezone.
    Input: 10:27 UTC -> UTC+2: 12:27.
    """
    res = format_datetime("2026-10-25T10:27:00")
    assert res == "Oct 25, 12:27"


def test_format_datetime_timezone_aware_string(deterministic_timezone):
    """
    Test timezone-aware strings (trailing Z or +00:00).
    Input: 10:27 UTC -> UTC+2: 12:27.
    """
    res_z = format_datetime("2026-10-25T10:27:00Z")
    assert res_z == "Oct 25, 12:27"

    res_offset = format_datetime("2026-10-25T10:27:00+00:00")
    assert res_offset == "Oct 25, 12:27"


def test_format_datetime_datetime_object(deterministic_timezone):
    """Test datetime objects (naive and timezone-aware)."""
    # Naive datetime: treated as UTC
    dt_naive = datetime(2026, 10, 25, 10, 27, 0)
    assert format_datetime(dt_naive) == "Oct 25, 12:27"

    # Aware datetime in UTC
    dt_aware = datetime(2026, 10, 25, 10, 27, 0, tzinfo=timezone.utc)
    assert format_datetime(dt_aware) == "Oct 25, 12:27"


def test_format_datetime_invalid_input():
    """Test invalid input does not crash and returns graceful string or '-'."""
    assert format_datetime("invalid-timestamp-string") == "invalid-timestamp-string"
    assert format_datetime(12345) == "-"
    assert format_datetime([]) == "-"


def test_color_and_category_tokens():
    """Test display colors and category constants."""
    for s in ("open", "in_progress", "resolved", "closed"):
        assert s in STATUS_COLORS
        assert STATUS_COLORS[s].startswith("#")

    for p in ("low", "medium", "high", "urgent"):
        assert p in PRIORITY_COLORS
        assert PRIORITY_COLORS[p].startswith("#")

    assert set(CATEGORY_OPTIONS) == {"network", "hardware", "software", "access", "email", "other"}
