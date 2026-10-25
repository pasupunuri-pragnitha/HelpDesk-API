"""Helper module for formatting timestamps and display tokens in the dashboard."""

from datetime import datetime, timezone
from typing import Any

STATUS_COLORS: dict[str, str] = {
    "open": "#3182ce",        # Blue
    "in_progress": "#dd6b20", # Orange
    "resolved": "#38a169",    # Green
    "closed": "#718096",      # Gray
}

PRIORITY_COLORS: dict[str, str] = {
    "urgent": "#e53e3e",      # Red
    "high": "#dd6b20",        # Orange
    "medium": "#3182ce",      # Blue
    "low": "#718096",         # Gray
}

CATEGORY_OPTIONS: list[str] = [
    "network",
    "hardware",
    "software",
    "access",
    "email",
    "other",
]


def get_local_timezone() -> Any:
    """Return the machine's local timezone."""
    return datetime.now().astimezone().tzinfo or timezone.utc


def format_datetime(value: Any) -> str:
    """
    Format timestamps into the viewer's local timezone.

    - Naive datetime/timestamps from the API are treated as UTC.
    - Converted to the machine's local timezone (.astimezone()).
    - Formatted as 'Oct 25, 12:27' (%b %d, %H:%M).
    - Returns '-' for None, empty, or unparseable non-string inputs.
    - Gracefully handles strings (ISO 8601 with/without timezone or 'Z') and datetime objects.
    - Handles invalid input without raising exceptions.
    """
    if value is None:
        return "-"

    if isinstance(value, str):
        val_str = value.strip()
        if not val_str or val_str.lower() in ("-", "none", "null"):
            return "-"
        try:
            clean_str = val_str[:-1] + "+00:00" if val_str.endswith("Z") else val_str
            dt = datetime.fromisoformat(clean_str)
        except (ValueError, TypeError):
            try:
                dt = datetime.strptime(val_str, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                return str(value)
    elif isinstance(value, datetime):
        dt = value
    else:
        return "-"

    # Treat naive values as UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    try:
        local_tz = get_local_timezone()
        local_dt = dt.astimezone(local_tz)
        return local_dt.strftime("%b %d, %H:%M")
    except Exception:
        return str(value)
