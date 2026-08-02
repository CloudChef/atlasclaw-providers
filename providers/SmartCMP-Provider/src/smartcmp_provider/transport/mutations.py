"""Classify non-idempotent SmartCMP write failures consistently."""

from __future__ import annotations

from smartcmp_provider.errors import SmartCmpError, SmartCmpUnknownOutcomeError


def write_result_is_unknown(error: SmartCmpError) -> bool:
    """Return whether a failed write may already have changed SmartCMP state.

    Provider transport attaches a structured mutation outcome at the point
    where it knows whether a request was sent or a response was received.
    Operations use this helper instead of parsing error text or inventing their
    own HTTP fallback rules.

    Args:
        error: Provider error raised while executing a non-idempotent request.

    Returns:
        ``True`` only when automatically repeating the write could duplicate or
        conflict with an upstream change.
    """

    if isinstance(error, SmartCmpUnknownOutcomeError):
        return True
    return error.mutation_outcome == "unknown"
