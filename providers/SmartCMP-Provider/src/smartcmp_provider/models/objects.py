"""Typed contracts for SmartCMP designer-object reads."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SmartCmpObjectType = Literal[
    "component_definition",
    "form_definition",
    "optimization_policy",
    "script_definition",
]


class ObjectReadQuery(BaseModel):
    """Select one supported SmartCMP object by its immutable internal ID."""

    model_config = ConfigDict(frozen=True)

    object_type: SmartCmpObjectType
    object_id: str


class ObjectReadResult(BaseModel):
    """Return one identity-verified SmartCMP object."""

    model_config = ConfigDict(frozen=True)

    object_type: SmartCmpObjectType
    object_id: str
    payload: dict[str, Any]


class ObjectIdQuery(BaseModel):
    """Select one designer object through a capability-specific Provider service."""

    model_config = ConfigDict(frozen=True)

    object_id: str = Field(min_length=1)


class ComponentFileView(BaseModel):
    """Return one validated component script file and its exact content."""

    model_config = ConfigDict(frozen=True)

    path: str
    type: str = ""
    mode: str = ""
    size: int = Field(ge=0)
    content: str


class ComponentDefinitionView(BaseModel):
    """Return the reusable component-script definition selected by object ID."""

    model_config = ConfigDict(frozen=True)

    object_id: str
    name: str = ""
    resource_type: str
    parent_type: str = ""
    component_family: str
    files: tuple[ComponentFileView, ...] = ()


class OptimizationPolicyView(BaseModel):
    """Return one validated SmartCMP cost-optimization policy definition."""

    model_config = ConfigDict(frozen=True)

    object_id: str
    name: str = ""
    definition: dict[str, Any]


class ScriptDefinitionView(BaseModel):
    """Return one validated SmartCMP script definition and complete source."""

    model_config = ConfigDict(frozen=True)

    object_id: str
    name: str = ""
    metadata: dict[str, Any]
    content: str
    language: str
