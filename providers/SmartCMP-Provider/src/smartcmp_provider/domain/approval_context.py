# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Build normalized SmartCMP pending approval context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from smartcmp_provider.domain.approval_specs import (
    extract_compute_profile_ids,
    extract_flavor_lookup_ids,
    extract_flavor_name_map,
    extract_named_resource_specs,
    unwrap_value,
)
from smartcmp_provider.domain.approval_validation import request_id_from_item
from smartcmp_provider.domain.object_operations import available_operation
from smartcmp_provider.models.object_operations import AvailableOperation


def available_approval_operations(
    request_id: str,
) -> tuple[AvailableOperation, ...]:
    """Return operations available for one current pending Request ID."""

    normalized_id = str(request_id or "").strip()
    if not normalized_id:
        return ()
    return (
        available_operation(
            "view_detail",
            "smartcmp.approvals.detail",
            arguments={"request_id": normalized_id},
        ),
        available_operation(
            "analyze",
            "smartcmp.approvals.analyze",
            arguments={"request_id": normalized_id},
        ),
        available_operation(
            "approve",
            "smartcmp.approvals.approve",
            arguments={"request_ids": [normalized_id]},
        ),
        available_operation(
            "reject",
            "smartcmp.approvals.reject",
            arguments={"request_ids": [normalized_id]},
            required_inputs=("reason",),
        ),
    )


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


def timestamp_sort_value(timestamp: Any) -> float:
    """Normalize supported SmartCMP timestamps for deterministic sorting."""

    if isinstance(timestamp, (int, float)) and timestamp > 0:
        return float(timestamp)
    if not isinstance(timestamp, str):
        return 0.0
    raw = timestamp.strip()
    if not raw:
        return 0.0
    try:
        numeric = float(raw)
    except ValueError:
        numeric = 0.0
    if numeric > 0:
        return numeric
    candidates = (raw, f"{raw[:-1]}+00:00") if raw.endswith("Z") else (raw,)
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp() * 1000
    for timestamp_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(raw, timestamp_format).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
        return parsed.timestamp() * 1000
    return 0.0


def sort_pending_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort pending approvals by visible update time, newest first."""

    indexed_items = list(enumerate(items))
    indexed_items.sort(
        key=lambda pair: (
            -timestamp_sort_value(
                pair[1].get("updatedDate") or pair[1].get("createdDate")
            ),
            pair[0],
        )
    )
    return [item for _, item in indexed_items]


def calculate_priority(
    item: dict[str, Any],
    *,
    now_ms: int,
) -> dict[str, Any]:
    """Calculate the existing SmartCMP queue priority and its evidence."""

    score = 50
    factors: list[str] = []
    wait_hours = calculate_wait_hours(item.get("createdDate"), now_ms)
    if wait_hours > 72:
        score += 30
        factors.append("wait_over_72h")
    elif wait_hours > 24:
        score += 15
        factors.append("wait_over_24h")
    if item.get("sla"):
        score += 20
        factors.append("has_sla")
    if item.get("chargePredictResult"):
        score += 10
        factors.append("has_cost_estimate")
    name = str(item.get("name") or "").lower()
    catalog = str(item.get("catalogName") or "").lower()
    keywords = ("urgent", "紧急", "生产", "prod", "critical", "重要")
    if any(keyword in name + catalog for keyword in keywords):
        score += 25
        factors.append("matched_high_priority_keyword")
    label = "high" if score >= 80 else "medium" if score >= 60 else "low"
    return {"score": score, "label": label, "factors": factors}


def request_params_from_item(item: dict[str, Any]) -> dict[str, Any]:
    """Extract request parameters from the current approval activity."""
    activity = item.get("currentActivity") or {}
    params = activity.get("requestParams") or {}
    return params if isinstance(params, dict) else {}


def items_need_flavor_lookup(items: list[dict[str, Any]]) -> bool:
    """Return whether any pending row needs flavor-name enrichment."""

    return any(
        extract_flavor_lookup_ids(request_params_from_item(item))
        for item in items
    )


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
    for key in ("infra_type", "resourceType", "cloudEntryType"):
        if key in data:
            value = _unwrap_value(data[key])
            if value and value != "vsphere":
                specs.append(f"resource_type={value}")
                break
    if "asset_tag" in data:
        _append("asset_tag", data["asset_tag"])


def _first_text(*values: Any) -> str:
    for value in values:
        normalized = _unwrap_value(value)
        if isinstance(normalized, (str, int, float)):
            text = str(normalized).strip()
            if text:
                return text
    return ""


def _item_needs_flavor_lookup(item: dict[str, Any]) -> bool:
    return items_need_flavor_lookup([item])


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
