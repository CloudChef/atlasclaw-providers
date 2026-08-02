"""Typed inputs and outputs for SmartCMP approval operations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ApprovalDecision = Literal["approve", "reject"]
ApprovalDecisionOutcome = Literal["succeeded", "failed", "unknown"]


class ApprovalListQuery(BaseModel):
    """Describe one bounded pending-approval query."""

    model_config = ConfigDict(frozen=True)

    days: int | None = Field(default=None, ge=1)
    page_size: int = Field(default=50, ge=1)
    max_pages: int = Field(default=1, ge=1)


class ApprovalListResult(BaseModel):
    """Return raw pending rows and the upstream total count."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, Any], ...] = ()
    total: int = 0


class ApprovalQueueResult(BaseModel):
    """Return sorted pending rows with optional display enrichment."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, Any], ...] = ()
    total: int = 0
    flavor_names_by_id: dict[str, str] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()


class ApprovalDetailQuery(BaseModel):
    """Select one pending approval by its user-facing Request ID."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    days: int = Field(default=90, ge=1)
    max_attempts: int = Field(default=5, ge=1)
    retry_interval_seconds: float = Field(default=3.0, ge=0)


class ApprovalDetailResult(BaseModel):
    """Return the exact pending row resolved from a visible Request ID."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    item: dict[str, Any]


class ApprovalDecisionInput(BaseModel):
    """Describe one confirmed, non-idempotent approval decision."""

    model_config = ConfigDict(frozen=True)

    decision: ApprovalDecision
    request_ids: tuple[str, ...] = Field(min_length=1)
    reason: str = ""
    max_pages: int = Field(default=5, ge=1)


class ApprovalDecisionItem(BaseModel):
    """Report one visible Request ID outcome without internal activity IDs."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    outcome: ApprovalDecisionOutcome
    status: str = ""
    message: str = ""


class ApprovalDecisionResult(BaseModel):
    """Return item-level results from one non-retried batch decision."""

    model_config = ConfigDict(frozen=True)

    decision: ApprovalDecision
    reason: str = ""
    items: tuple[ApprovalDecisionItem, ...]
    overall_success: bool
