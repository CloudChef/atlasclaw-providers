# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Shared helpers for reading SmartCMP pending approval context."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import requests

from _approval_specs import (
    extract_compute_profile_ids,
    extract_flavor_lookup_ids,
    extract_flavor_name_map,
    extract_named_resource_specs,
    unwrap_value,
)
from _approval_validation import request_id_from_item


RequestGet = Callable[..., Any]
SleepFn = Callable[[float], None]
TimeFn = Callable[[], float]


@dataclass(frozen=True)
class ApprovalContext:
    """Normalized view of one pending SmartCMP approval item.

    The raw ``item`` is kept so callers can still build provider action URLs
    from SmartCMP-specific fields. The ``meta`` dictionary contains only the
    stable fields exposed to the agent and UI.
    """

    item: dict[str, Any]
    meta: dict[str, Any]


def format_timestamp(ts: Any) -> str:
    """Format a SmartCMP millisecond timestamp for human-readable output."""
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    return str(ts) if ts else ""


def calculate_wait_hours(created_ts: Any, now_ms: int) -> float:
    """Return elapsed hours from SmartCMP creation time to ``now_ms``."""
    if isinstance(created_ts, (int, float)) and created_ts > 0:
        return round((now_ms - created_ts) / 3600000, 1)
    return 0.0


def request_params_from_item(item: dict[str, Any]) -> dict[str, Any]:
    """Extract request parameters from the current approval activity."""
    activity = item.get("currentActivity") or {}
    params = activity.get("requestParams") or {}
    return params if isinstance(params, dict) else {}


def extract_catalog_id(item: dict[str, Any]) -> str:
    """Return the service catalog ID if the approval row exposes one."""
    catalog = item.get("catalog") or {}
    params = request_params_from_item(item)
    return _first_text(
        item.get("catalogId"),
        item.get("catalogID"),
        item.get("catalog_id"),
        catalog.get("id") if isinstance(catalog, dict) else "",
        params.get("catalogId"),
        params.get("catalog_id"),
    )


def extract_resource_specs(
    item: dict[str, Any],
    *,
    flavor_names_by_id: dict[str, str] | None = None,
) -> list[str]:
    """Extract concise resource sizing facts from SmartCMP request params."""
    params = request_params_from_item(item)
    named_specs = extract_named_resource_specs(params)
    if named_specs:
        return named_specs[:8]
    flavor_names_by_id = flavor_names_by_id or {}
    compute_profile_ids = extract_compute_profile_ids(params)
    flavor_names = [
        flavor_names_by_id[profile_id]
        for profile_id in compute_profile_ids
        if profile_id in flavor_names_by_id
    ]
    if compute_profile_ids:
        return flavor_names[:8]

    specs: list[str] = []
    for key, value in params.items():
        if key.startswith("_ra_Compute_") or key.startswith("_ra_"):
            continue
        if isinstance(value, dict):
            _extract_from_dict(value, specs)

    resource_specs = params.get("resourceSpecs") or {}
    if isinstance(resource_specs, dict):
        for node_spec in resource_specs.values():
            if isinstance(node_spec, dict):
                _extract_from_dict(node_spec, specs)

    ext_params = params.get("extensibleParameters") or {}
    if isinstance(ext_params, dict):
        for node_spec in ext_params.values():
            if isinstance(node_spec, dict):
                _extract_from_dict(node_spec, specs)

    compute_profile = params.get("_ra_Compute_compute_profile_id")
    if compute_profile:
        specs.append(f"compute_profile={compute_profile}")

    for key in ("quantity", "count", "instanceCount", "serverCount"):
        if key in params and params[key]:
            specs.append(f"quantity={params[key]}")
            break

    deduped: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        if spec in seen:
            continue
        seen.add(spec)
        deduped.append(spec)
    return deduped[:8]


def extract_cost_info(item: dict[str, Any]) -> str:
    """Return a short cost estimate string from a SmartCMP approval row."""
    charge = item.get("chargePredictResult")
    if isinstance(charge, dict):
        total = charge.get("totalCost") or charge.get("cost") or charge.get("amount")
        if total not in (None, ""):
            return f"¥{total}"
    if charge:
        return str(charge)
    return "not_estimated"


def get_approval_step_name(item: dict[str, Any]) -> str:
    """Return the current SmartCMP approval step display name."""
    activity = item.get("currentActivity") or {}
    step = activity.get("processStep") or {}
    return str(step.get("name") or "step_unavailable")


def get_approver_info(item: dict[str, Any]) -> str:
    """Return up to three current approver names for display and analysis."""
    activity = item.get("currentActivity") or {}
    approvers: list[str] = []
    approval_requests = activity.get("approvalRequests") or []
    for approval_request in approval_requests[:3]:
        approver = approval_request.get("approver") or {}
        name = approver.get("name") or approver.get("loginId") or ""
        if name:
            approvers.append(str(name))
    if approvers:
        return ", ".join(approvers)

    assignments = activity.get("assignments") or []
    for assignment in assignments[:3]:
        approver = assignment.get("approver") or {}
        name = approver.get("name") or approver.get("loginId") or ""
        if name:
            approvers.append(str(name))
    return ", ".join(approvers) if approvers else "approver_unavailable"


def request_id(item: dict[str, Any]) -> str:
    """Return the SmartCMP user-facing request number, not an internal UUID."""
    return request_id_from_item(item)


def fetch_flavor_names_by_id(
    base_url: str,
    headers: dict[str, str],
    *,
    request_get: RequestGet = requests.get,
) -> dict[str, str]:
    """Fetch SmartCMP flavor names needed to render compute profile specs."""
    try:
        resp = request_get(
            f"{base_url}/flavors",
            headers=headers,
            params={"page": 1, "size": 500, "query": "", "queryValue": "", "sort": "createdDate,desc"},
            verify=False,
            timeout=30,
        )
        resp.raise_for_status()
        return extract_flavor_name_map(resp.json())
    except requests.exceptions.RequestException:
        return {}


def query_pending_items(
    base_url: str,
    headers: dict[str, str],
    days: int,
    *,
    request_get: RequestGet = requests.get,
    time_fn: TimeFn = time.time,
) -> list[dict[str, Any]]:
    """Query pending approvals in SmartCMP's current activity approval API."""
    now_ms = int(time_fn() * 1000)
    start_of_today = now_ms - (now_ms % 86400000)
    start_at_min = start_of_today - (days * 86400000)
    start_at_max = now_ms
    url = f"{base_url}/generic-request/current-activity-approval"
    all_items: list[dict[str, Any]] = []
    for page in range(1, 6):
        params = {
            "page": page,
            "size": 50,
            "stage": "pending",
            "sort": "updatedDate,desc",
            "startAtMin": start_at_min,
            "startAtMax": start_at_max,
            "rangeField": "updatedDate",
            "states": "",
        }
        response = request_get(url, headers=headers, params=params, verify=False, timeout=30)
        response.raise_for_status()
        items = _extract_items(response.json())
        if not items:
            break
        all_items.extend(items)
        if len(items) < 50:
            break
    return all_items


def load_pending_approval_context(
    base_url: str,
    headers: dict[str, str],
    identifier: str,
    days: int,
    *,
    request_get: RequestGet = requests.get,
    sleep_fn: SleepFn = time.sleep,
    time_fn: TimeFn = time.time,
    max_attempts: int = 5,
    retry_interval: int = 3,
) -> ApprovalContext | None:
    """Load and normalize one pending approval by SmartCMP Request ID."""
    matched: dict[str, Any] | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            items = query_pending_items(
                base_url,
                headers,
                days,
                request_get=request_get,
                time_fn=time_fn,
            )
        except requests.exceptions.RequestException:
            if attempt == max_attempts:
                raise
            sleep_fn(retry_interval)
            continue

        matched = next((item for item in items if _matches_identifier(item, identifier)), None)
        if matched is not None:
            break

        if attempt < max_attempts:
            print(
                f"[DEBUG] Attempt {attempt}/{max_attempts}: identifier {identifier} "
                f"not found in pending list, retrying in {retry_interval}s..."
            )
            sleep_fn(retry_interval)

    if matched is None:
        return None

    flavor_names_by_id = (
        fetch_flavor_names_by_id(base_url, headers, request_get=request_get)
        if _item_needs_flavor_lookup(matched)
        else {}
    )
    return ApprovalContext(
        item=matched,
        meta=build_approval_context_meta(
            matched,
            now_ms=int(time_fn() * 1000),
            flavor_names_by_id=flavor_names_by_id,
        ),
    )


def build_approval_context_meta(
    item: dict[str, Any],
    *,
    now_ms: int,
    flavor_names_by_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build stable approval metadata for detail and analysis responses."""
    name = item.get("name") or item.get("requestName") or "N/A"
    catalog = item.get("catalogName") or item.get("resourceType") or item.get("type") or "uncategorized_request"
    applicant = item.get("applicant") or item.get("requesterName") or item.get("createdByName") or "N/A"
    created_date = item.get("createdDate") or ""
    updated_date = item.get("updatedDate") or ""
    return {
        "requestId": request_id(item),
        "name": name,
        "catalogId": extract_catalog_id(item),
        "catalogName": catalog,
        "applicant": applicant,
        "email": item.get("email") or "",
        "description": item.get("description") or item.get("justification") or "",
        "createdDate": created_date,
        "updatedDate": updated_date,
        "waitHours": calculate_wait_hours(created_date, now_ms),
        "approvalStep": get_approval_step_name(item),
        "currentApprover": get_approver_info(item),
        "costEstimate": extract_cost_info(item),
        "resourceSpecs": extract_resource_specs(
            item,
            flavor_names_by_id=flavor_names_by_id,
        ),
        "requestParams": request_params_from_item(item),
    }


def _unwrap_value(value: Any) -> Any:
    return unwrap_value(value)


def _extract_from_dict(data: dict[str, Any], specs: list[str]) -> None:
    def _append(key: str, value: Any) -> None:
        normalized = _unwrap_value(value)
        if normalized not in (None, ""):
            specs.append(f"{key}={normalized}")

    for key in ("cpu", "vcpu", "cpuCount", "cpu_count"):
        if key in data:
            value = _unwrap_value(data[key])
            if value:
                specs.append(f"cpu_cores={value}")
                break
    for key in ("memory", "ram", "memorySize", "memory_size"):
        if key in data:
            value = _unwrap_value(data[key])
            if value:
                specs.append(f"memory={value}")
                break
    for key in ("disk", "storage", "diskSize", "disk_size"):
        if key in data:
            _append("storage", data[key])
            break
    if "asset_tag" in data:
        _append("asset_tag", data["asset_tag"])
    for key in ("infra_type", "resourceType", "cloudEntryType"):
        if key in data:
            value = _unwrap_value(data[key])
            if value and value != "vsphere":
                specs.append(f"resource_type={value}")
                break


def _first_text(*values: Any) -> str:
    for value in values:
        normalized = _unwrap_value(value)
        if isinstance(normalized, (str, int, float)):
            text = str(normalized).strip()
            if text:
                return text
    return ""


def _item_needs_flavor_lookup(item: dict[str, Any]) -> bool:
    return bool(extract_flavor_lookup_ids(request_params_from_item(item)))


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("content", "data", "items", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _matches_identifier(item: dict[str, Any], identifier: str) -> bool:
    normalized = identifier.strip().lower()
    return bool(normalized and request_id(item).lower() == normalized)
