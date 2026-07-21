#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Shared SmartCMP resource target parsing and exact-name resolution."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 20


class ResourceResolutionError(ValueError):
    """Describe a user-correctable resource selection without exposing internal IDs."""


def parse_resource_directory(raw_value: Any) -> list[dict[str, Any]]:
    """Extract resource-list metadata from direct JSON or workflow context.

    Args:
        raw_value: JSON text or an already-decoded workflow/list payload.

    Returns:
        Resource directory entries that contain an internal target identifier.

    Raises:
        ResourceResolutionError: If a non-empty JSON string is invalid.
    """
    if raw_value in (None, ""):
        return []
    payload = raw_value
    if isinstance(raw_value, str):
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ResourceResolutionError("Resource list metadata is not valid JSON.") from exc
    return [
        item
        for item in _extract_directory_items(payload)
        if isinstance(item, dict) and resource_id(item)
    ]


def resolve_resource_targets(
    *,
    resource_ids: list[str],
    resource_names: list[str],
    resource_index: int | None,
    directory_items: list[dict[str, Any]],
    trigger_source: str,
    search_page: Callable[[int, int, str], Any] | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve internal IDs, a list index, or exact visible names.

    Args:
        resource_ids: Compatibility-only internal identifiers supplied by a backend flow.
        resource_names: Case-sensitive visible names after caller-side whitespace trimming.
        resource_index: One-based index from the latest resource list.
        directory_items: Hidden metadata from the latest resource list.
        trigger_source: Request source used only for structured workflow metadata.
        search_page: Callback returning one CMP search page for ``page, size, query``.
        page_size: Number of resources requested per CMP page.
        max_pages: Safety limit for CMP pagination.

    Returns:
        Internal IDs, name-first request metadata, and structured resolved metadata.

    Raises:
        ResourceResolutionError: If the target is absent, ambiguous, or inconsistent.
    """
    if resource_ids:
        return (
            resource_ids,
            [
                {"name": "", "index": None, "source": _request_source(trigger_source)}
                for _resource_id in resource_ids
            ],
            [
                {
                    "name": "",
                    "index": None,
                    "status": "",
                    "type": "",
                    "scope": "",
                    "resourceId": target_id,
                }
                for target_id in resource_ids
            ],
        )

    if directory_items and (resource_names or resource_index is not None):
        selected = resolve_from_directory(
            resource_names=resource_names,
            resource_index=resource_index,
            directory_items=directory_items,
        )
        return build_resolved_request(
            selected,
            source="resource_directory",
            include_request_index=resource_index is not None,
        )

    if resource_index is not None:
        raise ResourceResolutionError(
            f"No recent resource list metadata is available for index {resource_index}. "
            "List resources first or provide the exact resource name."
        )

    if resource_names:
        if search_page is None:
            raise ResourceResolutionError("SmartCMP resource search is unavailable.")
        resolved = []
        for name in resource_names:
            resolved.append(
                resolve_exact_resource_name(
                    name,
                    search_page=search_page,
                    page_size=page_size,
                    max_pages=max_pages,
                )
            )
        return build_resolved_request(
            resolved,
            source="resource_search",
            include_request_index=False,
        )

    raise ResourceResolutionError(
        "Provide an exact resource name or select a resource from the latest resource table."
    )


def resolve_single_resource(
    *,
    resource_id_value: str,
    resource_name: str,
    resource_index: int | None,
    directory_items: list[dict[str, Any]],
    search_page: Callable[[int, int, str], Any] | None = None,
) -> tuple[str, str]:
    """Resolve one resource for tools whose public contract is single-target.

    Args:
        resource_id_value: Compatibility-only internal identifier.
        resource_name: Exact case-sensitive visible name.
        resource_index: One-based index from the latest resource list.
        directory_items: Latest list metadata.
        search_page: Callback returning one CMP search page.

    Returns:
        Internal resource ID and visible name.

    Raises:
        ResourceResolutionError: If no unique target can be resolved.
    """
    normalized_id = str(resource_id_value or "").strip()
    normalized_name = str(resource_name or "").strip()
    ids, _requested, resolved = resolve_resource_targets(
        resource_ids=[normalized_id] if normalized_id else [],
        resource_names=[normalized_name] if normalized_name else [],
        resource_index=resource_index,
        directory_items=directory_items,
        trigger_source="user",
        search_page=search_page,
    )
    return ids[0], str(resolved[0].get("name") or normalized_name).strip()


def resolve_from_directory(
    *,
    resource_names: list[str],
    resource_index: int | None,
    directory_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Select exact targets from recent hidden resource-list metadata.

    Args:
        resource_names: Exact, case-sensitive visible names.
        resource_index: Optional one-based resource-list index.
        directory_items: Latest resource-list metadata.

    Returns:
        Selected directory items.

    Raises:
        ResourceResolutionError: If an index/name is absent, duplicated, or inconsistent.
    """
    selected_items: list[dict[str, Any]] = []
    if resource_index is not None:
        if resource_index <= 0:
            raise ResourceResolutionError("Resource index must be a positive integer.")
        selected = next(
            (item for item in directory_items if directory_index(item) == resource_index),
            None,
        )
        if selected is None:
            raise ResourceResolutionError(
                f"No listed resource matched index {resource_index}. "
                f"Available resources:\n{format_resource_choices(directory_items)}"
            )
        selected_items = [selected]

    if resource_names:
        name_matches = [item for item in directory_items if display_name(item) in resource_names]
        for name in resource_names:
            exact_matches = [item for item in directory_items if display_name(item) == name]
            if not exact_matches:
                raise ResourceResolutionError(
                    f"No listed resource exactly matched name '{name}'. "
                    f"Available resources:\n{format_resource_choices(directory_items)}"
                )
            if len(exact_matches) > 1 and resource_index is None:
                raise ResourceResolutionError(
                    f"Multiple listed resources exactly matched name '{name}'. "
                    f"Choose one by table #:\n{format_resource_choices(exact_matches)}"
                )

        if selected_items:
            selected_name = display_name(selected_items[0])
            if selected_name not in resource_names:
                raise ResourceResolutionError(
                    "Selected resource does not match the provided name. "
                    f"Index {resource_index} is '{selected_name}', "
                    f"but the requested name was '{resource_names[0]}'."
                )
        else:
            selected_items = name_matches
    return selected_items


def resolve_exact_resource_name(
    name: str,
    *,
    search_page: Callable[[int, int, str], Any],
    candidate_filter: Callable[[dict[str, Any]], bool] | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> dict[str, Any]:
    """Resolve one case-sensitive name through bounded client-side pagination.

    CMP deployments can ignore ``queryValue``. Every returned page is therefore
    filtered client-side, and duplicate internal IDs are collapsed before the
    ambiguity check.

    Args:
        name: Exact visible name after whitespace trimming.
        search_page: Callback returning a page list or ``(items, total)`` tuple.
        candidate_filter: Optional trusted metadata selector used by internal
            enrichment flows after exact-name matching.
        page_size: Requested page size.
        max_pages: Maximum pages inspected.

    Returns:
        The unique matching summary.

    Raises:
        ResourceResolutionError: If the name is absent or duplicated.
    """
    normalized_name = str(name or "").strip()
    visible_items = collect_paginated_resource_summaries(
        search_page=search_page,
        query=normalized_name,
        page_size=page_size,
        max_pages=max_pages,
    )
    exact_matches = [
        item for item in visible_items if resource_id(item) and display_name(item) == normalized_name
    ]

    if candidate_filter is not None:
        exact_matches = [item for item in exact_matches if candidate_filter(item)]

    if not exact_matches:
        choices = format_resource_choices(visible_items[:20])
        if choices:
            raise ResourceResolutionError(
                f"No SmartCMP resource exactly matched name '{normalized_name}'. "
                f"Closest visible matches:\n{choices}"
            )
        raise ResourceResolutionError(
            f"No SmartCMP resource exactly matched name '{normalized_name}'."
        )
    if len(exact_matches) > 1:
        raise ResourceResolutionError(
            f"Multiple SmartCMP resources exactly matched name '{normalized_name}'. "
            f"Choose one by table #:\n{format_resource_choices(exact_matches)}"
        )
    return exact_matches[0]


def collect_paginated_resource_summaries(
    *,
    search_page: Callable[[int, int, str], Any],
    query: str = "",
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[dict[str, Any]]:
    """Collect de-duplicated CMP resource summaries with bounded pagination.

    Args:
        search_page: Callback returning a page list or ``(items, total)`` tuple.
        query: Optional server-side hint; callers must still filter client-side.
        page_size: Requested CMP page size.
        max_pages: Maximum pages inspected.

    Returns:
        De-duplicated summaries in CMP page order.
    """
    visible_items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    scanned = 0
    for page in range(1, max_pages + 1):
        raw_page = search_page(page, page_size, query)
        items, total = _unpack_search_page(raw_page)
        if not items:
            break
        scanned += len(items)
        for item in items:
            item_id = resource_id(item)
            identity = item_id or f"{display_name(item)}\0{display_status(item)}\0{display_type(item)}"
            if identity in seen_ids:
                continue
            seen_ids.add(identity)
            visible_items.append(item)
        if total is not None and scanned >= total:
            break
        if total is None and len(items) < page_size:
            break
    return visible_items


def build_resolved_request(
    items: list[dict[str, Any]],
    *,
    source: str,
    include_request_index: bool,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build structured target metadata while keeping internal IDs out of prose.

    Args:
        items: Resolved SmartCMP summaries.
        source: Resolver source label.
        include_request_index: Whether the user selected a visible index.

    Returns:
        Internal IDs, request metadata, and resolved workflow metadata.

    Raises:
        ResourceResolutionError: If none of the selected items has an internal ID.
    """
    target_ids: list[str] = []
    requested_resources: list[dict[str, Any]] = []
    resolved_resources: list[dict[str, Any]] = []
    for item in items:
        target_id = resource_id(item)
        if not target_id or target_id in target_ids:
            continue
        target_ids.append(target_id)
        index = directory_index(item)
        name = display_name(item)
        requested_resources.append(
            {
                "name": name,
                "index": index if include_request_index else None,
                "source": source,
            }
        )
        resolved_resources.append(
            {
                "name": name,
                "index": index,
                "status": display_status(item),
                "type": display_type(item),
                "scope": str(item.get("scope") or "").strip(),
                "resourceId": target_id,
            }
        )
    if not target_ids:
        raise ResourceResolutionError("No resolvable resource was selected.")
    return target_ids, requested_resources, resolved_resources


def resource_id(item: dict[str, Any]) -> str:
    """Return the structured internal resource identifier for a summary."""
    return str(item.get("id") or item.get("resourceId") or "").strip()


def display_name(item: dict[str, Any]) -> str:
    """Return the preferred user-visible resource name."""
    return str(
        item.get("name")
        or item.get("nameZh")
        or item.get("displayName")
        or item.get("label")
        or item.get("instanceName")
        or "unknown resource"
    ).strip()


def display_status(item: dict[str, Any]) -> str:
    """Return the preferred user-visible resource status."""
    return str(
        item.get("status")
        or item.get("powerState")
        or item.get("state")
        or item.get("phase")
        or "unknown"
    ).strip()


def display_type(item: dict[str, Any]) -> str:
    """Return the preferred user-visible resource type."""
    return str(item.get("componentType") or item.get("resourceType") or item.get("type") or "unknown").strip()


def directory_index(item: dict[str, Any]) -> int | None:
    """Parse a list index from supported directory metadata fields."""
    value = item.get("index", item.get("#"))
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def escape_markdown_cell(value: Any) -> str:
    """Render an untrusted resource value safely inside a Markdown table cell."""
    rendered = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    return " ".join(rendered.split()).replace("|", "\\|")


def format_resource_choices(items: list[dict[str, Any]]) -> str:
    """Render name, status, and type choices without exposing internal IDs."""
    rows = []
    for fallback_index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        index = directory_index(item) or fallback_index
        rows.append(
            "| "
            + " | ".join(
                escape_markdown_cell(value)
                for value in (index, display_name(item), display_status(item), display_type(item))
            )
            + " |"
        )
    if not rows:
        return ""
    return "\n".join(
        [
            "| # | Name | Status | Type |",
            "| --- | --- | --- | --- |",
            *rows,
        ]
    )


def _extract_directory_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("resources", "items", "metadata", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    recent_metadata = payload.get("recent_tool_metadata")
    if isinstance(recent_metadata, list):
        for entry in reversed(recent_metadata):
            if not isinstance(entry, dict):
                continue
            if entry.get("tool_name") == "smartcmp_list_all_resource" and isinstance(
                entry.get("metadata"), list
            ):
                return entry["metadata"]
        for entry in reversed(recent_metadata):
            if isinstance(entry, dict) and isinstance(entry.get("metadata"), list):
                return entry["metadata"]
    return []


def _unpack_search_page(raw_page: Any) -> tuple[list[dict[str, Any]], int | None]:
    total: int | None = None
    items = raw_page
    if isinstance(raw_page, tuple) and len(raw_page) == 2:
        items, raw_total = raw_page
        try:
            total = int(raw_total)
        except (TypeError, ValueError):
            total = None
    if not isinstance(items, list):
        return [], total
    return [item for item in items if isinstance(item, dict)], total


def _request_source(trigger_source: str) -> str:
    return "webhook" if str(trigger_source or "").strip().lower() == "webhook" else "resource_id"
