"""Normalize SmartCMP timestamp representations for reusable domain projections."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def normalize_timestamp(value: Any) -> str:
    """Return a SmartCMP timestamp as a UTC ISO-8601 string when possible.

    Args:
        value: ISO text or a Unix timestamp in seconds or milliseconds.

    Returns:
        A UTC value with a trailing ``Z``; unrecognized non-empty text is
        preserved for compatibility.
    """

    if value in (None, ""):
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        numeric = stripped[1:] if stripped[:1] in {"+", "-"} else stripped
        if numeric.replace(".", "", 1).isdigit():
            return normalize_timestamp(float(stripped))
        try:
            parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            return stripped
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if abs(timestamp) >= 1_000_000_000_000:
            timestamp /= 1000.0
        return datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc,
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)
