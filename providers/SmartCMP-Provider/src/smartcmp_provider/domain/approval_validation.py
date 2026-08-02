# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Validate SmartCMP approval action identifiers."""

from __future__ import annotations

import re
from collections.abc import Iterable


APPROVAL_ID_FORMAT_HINT = (
    "Use the SmartCMP user-facing Request ID, such as RES20260505000010 or "
    "TIC20260502000003 or CHG20260413000011."
)

_PLACEHOLDER_MARKERS = (
    "dummy",
    "placeholder",
    "example",
    "sample",
    "todo",
    "xxx",
    "<",
    ">",
)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Z]{3}\d{14}$", re.IGNORECASE)
REQUEST_ID_FIELD_NAMES = (
    "requestId",
    "request_id",
    "workflowId",
    "workflow_id",
    "requestNo",
    "requestNumber",
    "customizedId",
)


def is_request_id(identifier: str) -> bool:
    """Return whether the identifier is a SmartCMP user-facing Request ID."""
    return bool(_REQUEST_ID_PATTERN.fullmatch(identifier.strip()))


def normalize_request_id(value: object) -> str:
    """Return a normalized SmartCMP Request ID or blank for non-request values."""
    candidate = str(value or "").strip()
    return candidate if is_request_id(candidate) else ""


def request_id_from_mapping(mapping: object) -> str:
    """Extract a user-facing Request ID from a SmartCMP response mapping."""
    if not isinstance(mapping, dict):
        return ""
    for field_name in REQUEST_ID_FIELD_NAMES:
        request_id = normalize_request_id(mapping.get(field_name))
        if request_id:
            return request_id
    return ""


def request_id_from_item(item: object) -> str:
    """Extract the canonical Request ID from known SmartCMP approval payload shapes."""
    if not isinstance(item, dict):
        return ""

    request_id = request_id_from_mapping(item)
    if request_id:
        return request_id

    current_activity = item.get("currentActivity")
    request_id = request_id_from_mapping(current_activity)
    if request_id:
        return request_id

    if isinstance(current_activity, dict):
        approval_requests = current_activity.get("approvalRequests")
        if isinstance(approval_requests, list):
            for approval_request in approval_requests:
                request_id = request_id_from_mapping(approval_request)
                if request_id:
                    return request_id
    return ""


def request_ids_from_item(item: object) -> tuple[str, ...]:
    """Extract all distinct Request IDs from known approval payload shapes.

    SmartCMP can repeat the same user-facing ID at the request, activity, and
    approval-request levels. Preserve source order while removing duplicates so
    callers can also detect conflicting IDs without depending on API operations.
    """

    if not isinstance(item, dict):
        return ()
    candidates: list[str] = []
    _extend_request_ids(candidates, item)
    current_activity = item.get("currentActivity")
    if isinstance(current_activity, dict):
        _extend_request_ids(candidates, current_activity)
        approval_requests = current_activity.get("approvalRequests")
        if isinstance(approval_requests, list):
            for approval_request in approval_requests:
                if isinstance(approval_request, dict):
                    _extend_request_ids(candidates, approval_request)

    distinct: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.casefold()
        if key in seen:
            continue
        seen.add(key)
        distinct.append(candidate)
    return tuple(distinct)


def invalid_approval_id_reason(approval_id: str) -> str | None:
    """Return why an approval action ID is unsafe, or None when it can be sent."""
    value = approval_id.strip()
    if not value:
        return "blank values are not SmartCMP Request IDs"
    if value.isdigit():
        return "display row numbers must be resolved to a SmartCMP Request ID before approval"
    if any(marker in value.lower() for marker in _PLACEHOLDER_MARKERS):
        return "placeholder values are not valid approval identifiers"
    if is_request_id(value):
        return None
    return (
        "expected a SmartCMP Request ID like RES20260505000010, "
        "TIC20260502000003, or CHG20260413000011"
    )


def find_invalid_approval_ids(ids: Iterable[str]) -> list[tuple[str, str]]:
    """Return invalid approval action identifiers with human-readable reasons."""
    invalid_ids: list[tuple[str, str]] = []
    for approval_id in ids:
        reason = invalid_approval_id_reason(approval_id)
        if reason:
            invalid_ids.append((approval_id, reason))
    return invalid_ids


def _extend_request_ids(target: list[str], mapping: dict[str, object]) -> None:
    for field_name in REQUEST_ID_FIELD_NAMES:
        request_id = normalize_request_id(mapping.get(field_name))
        if request_id:
            target.append(request_id)
