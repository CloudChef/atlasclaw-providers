"""Normalize transport settings shared by SmartCMP authentication and API calls."""

from __future__ import annotations

DEFAULT_TIMEOUT_SECONDS = 60.0


def coerce_timeout_seconds(
    value: object,
    *,
    default: float = DEFAULT_TIMEOUT_SECONDS,
) -> float:
    """Return a positive timeout value or the supplied Provider default.

    Args:
        value: Configured timeout value from an adapter or instance definition.
        default: Positive timeout used when ``value`` is absent or invalid.

    Returns:
        A positive timeout in seconds.

    Raises:
        ValueError: If ``default`` is not positive.
    """

    if default <= 0:
        raise ValueError("SmartCMP timeout default must be positive.")
    try:
        timeout = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return timeout if timeout > 0 else default
