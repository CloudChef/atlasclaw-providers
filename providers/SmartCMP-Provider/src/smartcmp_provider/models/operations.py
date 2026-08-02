"""Typed inputs and outputs for mutating SmartCMP resource operations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ResourceActionTarget(BaseModel):
    """Identify one SmartCMP resource in its user-scoped action endpoint."""

    model_config = ConfigDict(frozen=True)

    category: str
    resource_id: str


class ResourceActionInput(BaseModel):
    """Describe one confirmed no-parameter resource action."""

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
