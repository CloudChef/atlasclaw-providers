"""Stable inputs and outputs for SmartCMP resource operations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from smartcmp_provider.models.object_operations import AvailableOperation

ResourceScope = Literal["all_resources", "virtual_machines"]


class ResourceListQuery(BaseModel):
    """Describe one paginated SmartCMP resource directory query."""

    model_config = ConfigDict(frozen=True)

    scope: ResourceScope = "all_resources"
    query_value: str = ""
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1)


class ResourceListResult(BaseModel):
    """Return raw resource rows while keeping pagination metadata typed."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, Any], ...] = ()
    total: int | None = None


class ResourceDetailQuery(BaseModel):
    """Select one resource by internal ID or exact visible VM name."""

    model_config = ConfigDict(frozen=True)

    resource_id: str = ""
    resource_name: str = ""
    category: str = "virtual-machines"


class ResourceDetailResult(BaseModel):
    """Return the resolved internal ID and raw SmartCMP resource view."""

    model_config = ConfigDict(frozen=True)

    resource_id: str
    payload: dict[str, Any]


class ResourceDiskView(BaseModel):
    """Return one normalized disk row for resource detail rendering."""

    model_config = ConfigDict(frozen=True)

    name: str
    type: str = ""
    mode: str = ""
    size_gb: str = ""


class ResourceSectionView(BaseModel):
    """Return one named resource-detail section."""

    model_config = ConfigDict(frozen=True)

    title: str
    rows: tuple[tuple[str, str], ...]


class ResourceDetailView(BaseModel):
    """Return the normalized resource detail shared by all adapters."""

    model_config = ConfigDict(frozen=True)

    resource_id: str
    name: str
    status: str = ""
    cpu: str = ""
    memory_gb: str = ""
    ip_addresses: tuple[str, ...] = ()
    sections: tuple[ResourceSectionView, ...] = ()
    disks: tuple[ResourceDiskView, ...] = ()
    available_operations: tuple[AvailableOperation, ...] = ()


class ResourceOperationView(BaseModel):
    """Return one normalized user-executable resource operation."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=1)
    id: str
    name: str = ""
    name_zh: str = ""
    display_name: str
    category: str = ""
    type: str = ""
    support_batch_action: bool = False
    support_scheduled_task: bool = False
    available_operations: tuple[AvailableOperation, ...] = ()


class ResourceOperationsView(BaseModel):
    """Return normalized operations for one resource and category."""

    model_config = ConfigDict(frozen=True)

    category: str
    resource_id: str
    operations: tuple[ResourceOperationView, ...] = ()


class ResourceOperationsQuery(BaseModel):
    """Select the user-scoped operation endpoint for one resource."""

    model_config = ConfigDict(frozen=True)

    category: str = "virtual-machines"
    resource_id: str


class ResourceOperationsResult(BaseModel):
    """Return executable operation rows for the current user context."""

    model_config = ConfigDict(frozen=True)

    operations: tuple[dict[str, Any], ...] = ()


class ResourceSummarySearchQuery(BaseModel):
    """Describe one bounded shared-resource search request."""

    model_config = ConfigDict(frozen=True)

    params: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] | None = None


class ResourceEvidenceQuery(BaseModel):
    """Select resource evidence packs by internal SmartCMP resource IDs."""

    model_config = ConfigDict(frozen=True)

    resource_ids: tuple[str, ...] = ()


class ResourceEvidenceResult(BaseModel):
    """Return resource evidence records compatible with existing analyzers."""

    model_config = ConfigDict(frozen=True)

    records: tuple[dict[str, Any], ...] = ()


class ResourceComplianceQuery(BaseModel):
    """Select resources for generic compliance evidence analysis."""

    model_config = ConfigDict(frozen=True)

    resource_ids: tuple[str, ...] = Field(min_length=1)


class ResourceComplianceResult(BaseModel):
    """Return normalized generic compliance evidence for selected resources."""

    model_config = ConfigDict(frozen=True)

    analyzed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    analysis_contract: dict[str, Any]
    results: tuple[dict[str, Any], ...] = ()
