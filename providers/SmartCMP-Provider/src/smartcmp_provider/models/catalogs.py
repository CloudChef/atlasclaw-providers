"""Typed inputs and outputs for SmartCMP request catalog operations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CatalogListQuery(BaseModel):
    """Select published catalogs or one exact catalog for request discovery."""

    model_config = ConfigDict(frozen=True)

    keyword: str = ""
    catalog_id: str = ""
    page: int = Field(default=1, ge=1)
    size: int = Field(default=50, ge=1)


class CatalogListResult(BaseModel):
    """Return normalized request catalogs and upstream pagination metadata."""

    model_config = ConfigDict(frozen=True)

    catalogs: tuple[dict[str, Any], ...] = ()
    total: int = 0


class CatalogDetailQuery(BaseModel):
    """Select one catalog by its stable SmartCMP catalog ID."""

    model_config = ConfigDict(frozen=True)

    catalog_id: str


class CatalogDetailResult(BaseModel):
    """Return the raw catalog and normalized detail metadata."""

    model_config = ConfigDict(frozen=True)

    catalog: dict[str, Any]
    metadata: dict[str, Any]


class BusinessGroupQuery(BaseModel):
    """Select business groups available to one service catalog."""

    model_config = ConfigDict(frozen=True)

    catalog_id: str


class FacetQuery(BaseModel):
    """Select request facets for a business group and catalog node type."""

    model_config = ConfigDict(frozen=True)

    business_group_id: str
    node_type: str = "cloudchef.nodes.Compute"


class ResourceBundleQuery(BaseModel):
    """Select static request resource pools for one provisioning context."""

    model_config = ConfigDict(frozen=True)

    business_group_id: str
    component_type: str
    node_type: str
    cloud_entry_type_id: str = ""


class FlavorQuery(BaseModel):
    """Select machine flavors for an optional catalog and resource pool."""

    model_config = ConfigDict(frozen=True)

    query_value: str = ""
    resource_bundle_id: str = ""
    catalog_id: str = ""
    node_template_name: str = ""
    page: int = Field(default=1, ge=1)
    size: int = Field(default=100, ge=1)


class LogicalTemplateQuery(BaseModel):
    """Select logical templates for an optional provisioning context."""

    model_config = ConfigDict(frozen=True)

    query_value: str = ""
    resource_bundle_id: str = ""
    catalog_id: str = ""
    node_template_name: str = ""
    os_type: str = ""


class PhysicalTemplateQuery(BaseModel):
    """Select physical templates compatible with one logical template."""

    model_config = ConfigDict(frozen=True)

    resource_bundle_id: str
    logic_template_id: str


class ImageQuery(BaseModel):
    """Select images from one resource pool and logical-template context."""

    model_config = ConfigDict(frozen=True)

    resource_bundle_id: str
    logic_template_id: str
    cloud_entry_type: str


class CatalogItemsResult(BaseModel):
    """Return normalized catalog workflow choices without weakening item typing."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, Any], ...] = ()
