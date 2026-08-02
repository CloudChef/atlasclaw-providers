"""Safe typed views shared by AtlasClaw and MCP adapters."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from smartcmp_provider.models.object_operations import AvailableOperation


class RequestStatusView(BaseModel):
    """Return normalized request status without its raw internal record."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    name: str = ""
    catalog_name: str = ""
    state: str = ""
    provision_state: str = ""
    status_category: str = ""
    approval_passed: bool | None = None
    current_step: str = ""
    current_approver: str = ""
    error: str = ""
    resource_ids: tuple[str, ...] = ()
    created_date: int | None = None
    created_at: str = ""
    updated_date: int | None = None
    updated_at: str = ""


class ApprovalRequestEvidence(BaseModel):
    """Return user-relevant approval facts without workflow-internal IDs."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    name: str = ""
    catalog_name: str = ""
    description: str = ""
    state: str = ""
    approval_step: str = ""
    current_approver: str = ""
    applicant: str = ""
    created_date: int | None = None
    updated_date: int | None = None
    business_justification: str = ""
    resource_specifications: dict[str, Any] = Field(default_factory=dict)
    available_operations: tuple[AvailableOperation, ...] = ()


class PendingApprovalListView(BaseModel):
    """Return safe pending-approval summaries and their visible total."""

    model_config = ConfigDict(frozen=True)

    items: tuple[ApprovalRequestEvidence, ...] = ()
    total: int = 0


class ApprovalDetailView(BaseModel):
    """Return one safe approval selected by its visible Request ID."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    request: ApprovalRequestEvidence


class FlavorEvidence(BaseModel):
    """Return only approval-relevant flavor attributes."""

    model_config = ConfigDict(frozen=True)

    id: str = ""
    name: str = ""
    cpu: int | None = None
    memory_mb: int | None = None


class ApprovalAnalysisEvidence(BaseModel):
    """Return typed approval evidence for deterministic or Agent analysis."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    request: ApprovalRequestEvidence
    flavors: tuple[FlavorEvidence, ...] = ()
    warnings: tuple[str, ...] = ()
    analysis_instruction: str
