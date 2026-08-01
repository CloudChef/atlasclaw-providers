"""Adapter-neutral operations currently available for one SmartCMP object."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AvailableOperation(BaseModel):
    """Describe one state-valid SmartCMP capability for an exact object.

    ``tool_name`` identifies the MCP Tool that must also be present in
    ``tools/list``. ``arguments`` binds values already established by SmartCMP,
    while ``required_inputs`` names values the caller must still collect.
    Protocol adapters may add presentation metadata but must not reinterpret
    whether the operation is currently available.
    """

    model_config = ConfigDict(frozen=True)

    operation_id: str
    capability_id: str
    tool_name: str
    effect: Literal["read", "write"]
    confirmation: Literal["none", "user", "policy"]
    destructive: bool = False
    arguments: dict[str, Any] = Field(default_factory=dict)
    required_inputs: tuple[str, ...] = ()
