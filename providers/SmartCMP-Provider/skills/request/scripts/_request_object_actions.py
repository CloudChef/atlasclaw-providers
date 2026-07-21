# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Object metadata and actions owned by the SmartCMP request Domain Skill."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from _object_actions_common import (
    build_object_open_action,
    build_object_prompt_action,
    build_ui_hash_href,
    normalize_ui_base_url,
)


def build_catalog_object_actions(
    base_url: str,
    catalog: dict[str, Any],
) -> list[dict[str, object]]:
    """Build the actions currently available for one service catalog.

    Args:
        base_url: SmartCMP API or browser root.
        catalog: Catalog metadata containing its stable ID and display name.
    Returns:
        Provider-agnostic actions for the catalog object.
    """
    catalog_id = _text(catalog.get("id"))
    catalog_name = _text(catalog.get("nameZh") or catalog.get("name")) or catalog_id
    if not catalog_id:
        return []

    href = build_ui_hash_href(
        normalize_ui_base_url(base_url),
        f"#/main/catalog-ui/request/{quote(catalog_id, safe='')}",
    )
    actions: list[dict[str, object]] = []
    open_action = build_object_open_action(href)
    if open_action:
        actions.append(open_action)
    # Request is offered only when the producing Tool has authoritative state
    # proving that this catalog can currently be requested.
    if _catalog_is_requestable(catalog):
        request_action = build_object_prompt_action(
            "request",
            label_en="Request",
            label_zh="申请",
            prompt_en=f"Start a request for service catalog {catalog_name} ({catalog_id})",
            prompt_zh=f"申请服务目录 {catalog_name}（{catalog_id}）",
            effect="read",
            tone="success",
        )
        if request_action:
            actions.append(request_action)
    return actions


def attach_catalog_object_metadata(
    catalog: dict[str, Any],
    *,
    base_url: str,
) -> dict[str, Any]:
    """Attach the generic object-action contract to one catalog result.

    Args:
        catalog: Normalized catalog metadata returned by a request-domain Tool.
        base_url: SmartCMP API or browser root.
    Returns:
        A copy containing object identity and the current catalog actions.
    """
    enriched = dict(catalog)
    catalog_id = _text(catalog.get("id"))
    catalog_name = _text(catalog.get("nameZh") or catalog.get("name")) or catalog_id
    enriched.update(
        {
            "object_type": "catalog",
            "object_id": catalog_id,
            "object_name": catalog_name,
            "object_actions": build_catalog_object_actions(
                base_url,
                enriched,
            ),
        }
    )
    return enriched


def build_request_object_actions(
    base_url: str,
    request: dict[str, Any],
) -> list[dict[str, object]]:
    """Build the actions currently available for one submitted request.

    Args:
        base_url: SmartCMP API or browser root.
        request: Request detail containing its internal ID and application type.

    Returns:
        Provider-agnostic actions for the submitted request.
    """
    internal_id = _text(request.get("id"))
    application_type = _text(request.get("type"))
    if not internal_id or not application_type:
        return []
    href = build_ui_hash_href(
        normalize_ui_base_url(base_url),
        (
            "#/main/new-process/myApplication/"
            f"{quote(application_type, safe='')}/{quote(internal_id, safe='')}"
        ),
    )
    action = build_object_open_action(href)
    return [action] if action else []


def attach_request_object_metadata(
    status_meta: dict[str, Any],
    *,
    request: dict[str, Any],
    base_url: str,
) -> dict[str, Any]:
    """Attach the generic object-action contract to a request-status result.

    Args:
        status_meta: User-facing status projection.
        request: Raw request detail used only to build the verified page route.
        base_url: SmartCMP API or browser root.

    Returns:
        A copy containing request identity and currently available actions.
    """
    enriched = dict(status_meta)
    request_id = _text(status_meta.get("requestId"))
    request_name = _text(status_meta.get("name")) or request_id
    enriched.update(
        {
            "object_type": "request",
            "object_id": request_id,
            "object_name": request_name,
            "object_actions": build_request_object_actions(base_url, request),
        }
    )
    return enriched


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


def _catalog_is_requestable(catalog: dict[str, Any]) -> bool:
    """Derive request availability from the catalog state returned by SmartCMP."""
    state = _text(catalog.get("status") or catalog.get("state")).upper()
    return state == "PUBLISHED"
