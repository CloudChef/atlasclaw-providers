"""Typed inputs and outputs for shared SmartCMP directory queries."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DirectorySearchQuery(BaseModel):
    """Describe one standalone directory keyword query."""

    model_config = ConfigDict(frozen=True)

    query_value: str = ""
    page: int = Field(default=1, ge=1)
    size: int = Field(default=65_535, ge=1)


class ApplicationListQuery(BaseModel):
    """Select applications visible within one business group."""

    model_config = ConfigDict(frozen=True)

    business_group_id: str = Field(min_length=1)


class ComponentListQuery(BaseModel):
    """Select component metadata by catalog source key."""

    model_config = ConfigDict(frozen=True)

    source_key: str = Field(min_length=1)


class DirectoryItemsResult(BaseModel):
    """Return raw directory rows and an optional upstream total."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, Any], ...] = ()
    total: int | None = None
