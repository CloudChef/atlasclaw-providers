"""Shared SmartCMP business-group, resource-pool, application, and component queries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from smartcmp_provider.errors import SmartCmpValidationError
from smartcmp_provider.models.directory import (
    ApplicationListQuery,
    ComponentListQuery,
    DirectoryItemsResult,
    DirectorySearchQuery,
)
from smartcmp_provider.transport.client import SmartCmpClient


def build_business_group_directory_path(query: DirectorySearchQuery) -> str:
    """Build the standalone business-group directory path exactly."""

    encoded_query = quote(query.query_value, safe="")
    return (
        "/business-groups/has-update-permission"
        f"?query&sort=updatedDate%2Cdesc&page={query.page}&size={query.size}"
        f"&queryValue={encoded_query}"
    )


def build_resource_pool_directory_path(query: DirectorySearchQuery) -> str:
    """Build the standalone resource-pool directory path exactly."""

    encoded_query = quote(query.query_value, safe="")
    return (
        "/resource-bundles"
        f"?query&sort=createdDate%2Cdesc&page={query.page}&size={query.size}"
        f"&queryValue={encoded_query}"
    )


async def list_business_group_directory(
    client: SmartCmpClient,
    query: DirectorySearchQuery,
) -> DirectoryItemsResult:
    """List business groups visible to the current SmartCMP principal."""

    payload = await client.request_json(
        "GET",
        build_business_group_directory_path(query),
    )
    return _directory_result(payload, projector=_project_business_group)


async def list_resource_pool_directory(
    client: SmartCmpClient,
    query: DirectorySearchQuery,
) -> DirectoryItemsResult:
    """List standalone resource pools visible to the current principal."""

    payload = await client.request_json(
        "GET",
        build_resource_pool_directory_path(query),
    )
    return _directory_result(payload, projector=_project_resource_pool)


async def list_applications(
    client: SmartCmpClient,
    query: ApplicationListQuery,
) -> DirectoryItemsResult:
    """List applications for one selected SmartCMP business group."""

    business_group_id = query.business_group_id.strip()
    if not business_group_id:
        raise SmartCmpValidationError(
            "business_group_id is required.",
            trace_id=client.request.context.trace_id,
        )
    payload = await client.request_json(
        "GET",
        "/groups",
        params={"businessGroupIds": business_group_id},
    )
    return _directory_result(payload, projector=_project_application)


async def list_components(
    client: SmartCmpClient,
    query: ComponentListQuery,
) -> DirectoryItemsResult:
    """List component metadata for one catalog source key."""

    source_key = query.source_key.strip()
    if not source_key:
        raise SmartCmpValidationError(
            "source_key is required.",
            trace_id=client.request.context.trace_id,
        )
    payload = await client.request_json(
        "GET",
        "/components",
        params={"resourceType": source_key},
    )
    if _is_component_record(payload):
        return DirectoryItemsResult(
            items=(_project_component(payload),),
            total=1,
        )
    return _directory_result(
        payload,
        projector=_project_component,
    )


def _directory_result(
    payload: Any,
    *,
    projector: Callable[[dict[str, Any]], dict[str, Any]],
) -> DirectoryItemsResult:
    """Build a compact directory result from an endpoint-specific response."""

    items = _extract_items(payload)
    return DirectoryItemsResult(
        items=tuple(projector(item) for item in items),
        total=_extract_total(payload, len(items)),
    )


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("content", "items", "result", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        nested = _extract_items(value)
        if nested:
            return nested
    return []


def _is_component_record(payload: Any) -> bool:
    """Recognize the component endpoint's direct object response."""

    return isinstance(payload, dict) and any(
        str(payload.get(field) or "").strip()
        for field in ("id", "key", "sourceKey", "resourceType")
    )


def _project_business_group(item: dict[str, Any]) -> dict[str, Any]:
    """Keep business-group identity and hierarchy used for discovery."""

    return _project_fields(
        item,
        (
            "id",
            "name",
            "code",
            "description",
            "parentBusinessGroupId",
            "level",
            "rootLevel",
            "disabled",
        ),
    )


def _project_resource_pool(item: dict[str, Any]) -> dict[str, Any]:
    """Keep standalone resource-pool identity and platform type."""

    return _project_fields(
        item,
        (
            "id",
            "name",
            "description",
            "status",
            "cloudEntryId",
            "cloudEntryTypeId",
        ),
    )


def _project_application(item: dict[str, Any]) -> dict[str, Any]:
    """Keep application identity and its selected business-group scope."""

    return _project_fields(
        item,
        (
            "id",
            "name",
            "description",
            "status",
            "businessGroupId",
        ),
    )


def _project_component(item: dict[str, Any]) -> dict[str, Any]:
    """Keep component discovery metadata without blueprint definitions."""

    return _project_fields(
        item,
        (
            "id",
            "key",
            "sourceKey",
            "name",
            "nameZh",
            "description",
            "descriptionZh",
            "resourceType",
            "componentType",
            "version",
            "status",
            "published",
            "systemComponent",
            "enableMonitoring",
        ),
    )


def _project_fields(
    item: dict[str, Any],
    fields: tuple[str, ...],
) -> dict[str, Any]:
    """Copy only declared list fields while preserving false and zero values."""

    return {field: item[field] for field in fields if field in item}


def _extract_total(payload: Any, fallback: int) -> int:
    if isinstance(payload, dict):
        for key in ("totalElements", "total", "totalCount", "count"):
            try:
                return int(payload.get(key))
            except (TypeError, ValueError):
                pass
        for key in ("data", "result"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                nested_total = _extract_total(nested, fallback)
                if nested_total != fallback or any(
                    name in nested
                    for name in ("totalElements", "total", "totalCount", "count")
                ):
                    return nested_total
    return fallback
