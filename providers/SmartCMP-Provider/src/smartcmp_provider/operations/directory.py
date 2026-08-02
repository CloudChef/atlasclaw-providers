"""Shared SmartCMP business-group, resource-pool, application, and component queries."""

from __future__ import annotations

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
    return _directory_result(payload)


async def list_resource_pool_directory(
    client: SmartCmpClient,
    query: DirectorySearchQuery,
) -> DirectoryItemsResult:
    """List standalone resource pools visible to the current principal."""

    payload = await client.request_json(
        "GET",
        build_resource_pool_directory_path(query),
    )
    return _directory_result(payload)


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
    return _directory_result(payload)


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
    return _directory_result(payload)


def _directory_result(payload: Any) -> DirectoryItemsResult:
    items = _extract_items(payload)
    return DirectoryItemsResult(
        items=tuple(items),
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
