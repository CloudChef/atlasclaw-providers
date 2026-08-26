"""Typed inputs and outputs for shared SmartCMP directory queries."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DIRECTORY_LIST_PAGE_SIZE_MAX = 100


class DirectorySearchQuery(BaseModel):
    """Describe one bounded standalone directory keyword query."""

    model_config = ConfigDict(frozen=True)

    query_value: str = ""
    page: int = Field(default=1, ge=1, strict=True)
    size: int = Field(
        default=50,
        ge=1,
        le=DIRECTORY_LIST_PAGE_SIZE_MAX,
        strict=True,
    )


class ApplicationListQuery(BaseModel):
    """Select applications visible within one business group."""

    model_config = ConfigDict(frozen=True)

    business_group_id: str = Field(min_length=1)


class ComponentListQuery(BaseModel):
    """Select component metadata by catalog source key."""

    model_config = ConfigDict(frozen=True)

    source_key: str = Field(min_length=1)


class DirectoryItemsResult(BaseModel):
    """Return compact directory rows and an optional upstream total."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, Any], ...] = ()
    total: int | None = None
