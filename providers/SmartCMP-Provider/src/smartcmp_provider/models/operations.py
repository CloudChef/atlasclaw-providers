"""Typed inputs and outputs for mutating SmartCMP resource operations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResourceActionTarget(BaseModel):
    """Identify one SmartCMP resource in its user-scoped action endpoint."""

    model_config = ConfigDict(frozen=True)

    category: str
    resource_id: str


class ResourceActionInput(BaseModel):
    """Describe one confirmed action from the explicit Agent-supported set."""

    model_config = ConfigDict(frozen=True)

    targets: tuple[ResourceActionTarget, ...] = Field(min_length=1)
    action: str


class ResourceActionResult(BaseModel):
    """Report submission facts without echoing the raw upstream response."""

    model_config = ConfigDict(frozen=True)

    action: str
    resource_ids: tuple[str, ...]
    submitted: bool = True
    message: str
    verification_hint: str


class ResourceOperationInput(BaseModel):
    """Explicit non-interactive targets and parameters for a current-user operation."""

    model_config = ConfigDict(frozen=True)
    targets: tuple[ResourceActionTarget, ...] = Field(min_length=1)
    operation_id: str
    parameters: dict[str, Any] | None = None


class OperationTargetReceipt(BaseModel):
    """Retain target identity even when a batch acknowledgement is missing or failed."""

    model_config = ConfigDict(frozen=True)
    category: str
    resource_id: str
    task_ids: tuple[str, ...] = ()
    submitted: bool = False
    outcome: str = "unknown"
    error: str = ""


class OperationReceipt(BaseModel):
    """Single submission facts; task completion is intentionally a separate read."""

    model_config = ConfigDict(frozen=True)
    operation_id: str
    targets: tuple[OperationTargetReceipt, ...]
    affected_resources: tuple[dict[str, Any], ...] = ()
