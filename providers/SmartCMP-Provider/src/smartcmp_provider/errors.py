"""Provider-domain exceptions independent of AtlasClaw and MCP result formats."""

from __future__ import annotations

from typing import Literal

MutationOutcome = Literal["definite_failure", "unknown"]


class SmartCmpError(RuntimeError):
    """Base error raised by reusable SmartCMP provider operations.

    Args:
        message: User-safe summary of the provider failure.
        trace_id: Optional request correlation identifier for diagnostics.
    """

    def __init__(
        self,
        message: str,
        *,
        trace_id: str | None = None,
        http_status: int | None = None,
        mutation_outcome: MutationOutcome | None = None,
    ) -> None:
        super().__init__(message)
        self.trace_id = trace_id
        self.http_status = http_status
        self.mutation_outcome = mutation_outcome


class SmartCmpAuthenticationError(SmartCmpError):
    """Indicate that SmartCMP did not accept the resolved credential."""


class SmartCmpPermissionError(SmartCmpError):
    """Indicate that the authenticated principal cannot perform the operation."""


class SmartCmpValidationError(SmartCmpError):
    """Indicate that SmartCMP rejected externally supplied operation input."""


class SmartCmpTargetResolutionError(SmartCmpValidationError):
    """Indicate that a visible resource target is missing or ambiguous."""


class SmartCmpNotFoundError(SmartCmpError):
    """Indicate that the requested SmartCMP object does not exist or is not visible."""


class SmartCmpConflictError(SmartCmpError):
    """Indicate that the requested operation conflicts with current upstream state."""


class SmartCmpRateLimitError(SmartCmpError):
    """Indicate that SmartCMP throttled the operation."""


class SmartCmpTimeoutError(SmartCmpError):
    """Indicate that the operation exceeded its configured deadline."""


class SmartCmpUpstreamError(SmartCmpError):
    """Indicate a definite SmartCMP transport or service failure."""


class SmartCmpUnknownOutcomeError(SmartCmpError):
    """Indicate that a write may have reached SmartCMP but its result is unknown."""
