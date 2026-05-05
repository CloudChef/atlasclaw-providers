# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Shared resolution helpers for SmartCMP approval and rejection actions."""

from __future__ import annotations

from typing import Any

import requests

from _approval_validation import request_id_from_item


class ApprovalResolutionError(ValueError):
    """Raised when a Request ID cannot be resolved to a pending approval activity."""


def resolve_approval_action_ids(
    identifiers: list[str],
    *,
    base_url: str,
    headers: dict[str, str],
) -> list[str]:
    """Resolve user-facing Request IDs to CMP approval activity IDs for action APIs.

    The SmartCMP approval/rejection endpoints require ``currentActivity.id``. The skill
    contract exposes the stable user-facing Request ID instead, so this function queries the
    current pending approval list and translates each Request ID before execution.
    """
    pending_items = _query_pending_items(base_url=base_url, headers=headers)
    by_request_id = {
        request_id.lower(): item
        for item in pending_items
        if (request_id := _request_id(item))
    }

    resolved_ids: list[str] = []
    missing: list[str] = []
    missing_activity: list[str] = []
    for identifier in identifiers:
        item = by_request_id.get(identifier.lower())
        if item is None:
            missing.append(identifier)
            continue

        activity_id = _approval_activity_id(item)
        if not activity_id:
            missing_activity.append(identifier)
            continue
        resolved_ids.append(activity_id)

    if missing:
        joined = ", ".join(missing)
        raise ApprovalResolutionError(
            f"No pending SmartCMP approval matched Request ID(s): {joined}"
        )
    if missing_activity:
        joined = ", ".join(missing_activity)
        raise ApprovalResolutionError(
            f"Pending approval item(s) have no current activity ID: {joined}"
        )
    return resolved_ids


def _query_pending_items(*, base_url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    """Fetch current pending approval items from SmartCMP."""
    url = f"{base_url}/generic-request/current-activity-approval"
    all_items: list[dict[str, Any]] = []
    for page in range(1, 6):
        params = {
            "page": page,
            "size": 50,
            "stage": "pending",
            "sort": "updatedDate,desc",
            "states": "",
        }
        response = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
        response.raise_for_status()
        items = _extract_items(response.json())
        if not items:
            break
        all_items.extend(items)
        if len(items) < 50:
            break
    return all_items


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    """Extract a list of pending approval items from known SmartCMP response envelopes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("content", "data", "items", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _request_id(item: dict[str, Any]) -> str:
    """Return the user-facing SmartCMP Request ID for a pending item."""
    return request_id_from_item(item)


def _approval_activity_id(item: dict[str, Any]) -> str:
    """Return the current approval activity ID required by SmartCMP action APIs."""
    activity = item.get("currentActivity") or {}
    return str(activity.get("id") or "").strip()
