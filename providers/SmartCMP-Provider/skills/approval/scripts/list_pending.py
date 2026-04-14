# -*- coding: utf-8 -*-
"""List pending approval items from SmartCMP with enhanced details.

Usage:
  python list_pending.py [--days N]

Arguments:
  --days N    Query pending approvals updated within the last N days

Output:
  - Detailed list of pending approval items with priority analysis
  - ##APPROVAL_META_START## ... ##APPROVAL_META_END##
      JSON array with full structured info for agent processing

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python list_pending.py              # List all current pending approvals
  python list_pending.py --days 7     # List pending approvals updated in last 7 days

API Reference:
  GET /generic-request/current-activity-approval
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from typing import Any, Optional

import requests

try:
    from _common import require_config
except ImportError:
    import os

    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "scripts"),
    )
    from _common import require_config

def parse_days_from_argv(argv: list[str]) -> Optional[int]:
    """Parse optional --days argument from CLI argv."""
    for index, arg in enumerate(argv):
        if arg != "--days":
            continue
        if index + 1 >= len(argv):
            return None
        try:
            parsed = int(argv[index + 1])
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def build_pending_query_params(*, now_ms: int, days: Optional[int] = None) -> dict[str, Any]:
    """Build SmartCMP query params for pending approvals.

    Default behavior is to query all current pending approvals. A rolling time window is only
    applied when the caller explicitly passes ``--days``.
    """
    params: dict[str, Any] = {
        "page": 1,
        "size": 50,
        "stage": "pending",
        "sort": "updatedDate,desc",
        "states": "",
    }
    if days is None:
        return params

    start_of_today = now_ms - (now_ms % 86400000)
    start_at_min = start_of_today - (days * 86400000)
    params.update(
        {
            "startAtMin": start_at_min,
            "startAtMax": now_ms,
            "rangeField": "updatedDate",
        }
    )
    return params


def extract_list(data: Any) -> list[dict[str, Any]]:
    """Extract the list payload from a SmartCMP response envelope."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("content", "data", "items", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def format_timestamp(ts: Any) -> str:
    """Convert timestamp to readable date string."""
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(ts)
    return str(ts) if ts else ""


def calculate_wait_hours(created_ts: Any, *, now_ms: int) -> float:
    """Calculate waiting hours since creation."""
    if isinstance(created_ts, (int, float)) and created_ts > 0:
        hours = (now_ms - created_ts) / 3600000
        return round(hours, 1)
    return 0


def extract_from_dict(d: dict[str, Any], specs: list[str], prefix: str = "") -> None:
    """Helper to extract specs from a dictionary."""

    def get_value(val: Any) -> Any:
        if isinstance(val, dict) and "value" in val:
            return val["value"]
        return val

    for key in ["cpu", "vcpu", "cpuCount", "cpu_count"]:
        if key in d:
            value = get_value(d[key])
            if value:
                specs.append(f"CPU: {value}核")
                break

    for key in ["memory", "ram", "memorySize", "memory_size"]:
        if key in d:
            value = get_value(d[key])
            if value:
                if isinstance(value, (int, float)) and value >= 1024:
                    value = f"{value/1024:.1f}GB"
                elif isinstance(value, (int, float)):
                    value = f"{value}MB"
                specs.append(f"内存: {value}")
                break

    for key in ["disk", "storage", "diskSize", "disk_size"]:
        if key in d:
            value = get_value(d[key])
            if value:
                specs.append(f"存储: {value}")
                break

    if "tags" in d:
        tags_val = get_value(d["tags"])
        if isinstance(tags_val, dict) and tags_val:
            real_tags = {k: v for k, v in tags_val.items() if v is not None and v != ""}
            if real_tags:
                tag_str = ", ".join(f"{k}={v}" for k, v in list(real_tags.items())[:3])
                specs.append(f"标签: {tag_str}")

    for key in ["infra_type", "resourceType", "cloudEntryType"]:
        if key in d:
            value = get_value(d[key])
            if value and value != "vsphere":
                specs.append(f"类型: {value}")
                break

    if "asset_tag" in d:
        value = get_value(d["asset_tag"])
        if value:
            specs.append(f"资产标签: {value}")


def extract_resource_specs(item: dict[str, Any]) -> list[str]:
    """Extract resource specification summary from request params."""
    specs: list[str] = []
    activity = item.get("currentActivity") or {}
    params = activity.get("requestParams") or {}

    for key, val in params.items():
        if key.startswith("_ra_Compute_") or key.startswith("_ra_"):
            continue
        if isinstance(val, dict):
            extract_from_dict(val, specs)

    resource_specs = params.get("resourceSpecs") or {}
    if isinstance(resource_specs, dict):
        for node_name, node_spec in resource_specs.items():
            if isinstance(node_spec, dict):
                extract_from_dict(node_spec, specs, node_name)

    ext_params = params.get("extensibleParameters") or {}
    if isinstance(ext_params, dict):
        for node_name, node_spec in ext_params.items():
            if isinstance(node_spec, dict):
                extract_from_dict(node_spec, specs, node_name)

    compute_profile = params.get("_ra_Compute_compute_profile_id")
    if compute_profile:
        specs.append(f"计算配置: {compute_profile}")

    for key in ["quantity", "count", "instanceCount", "serverCount"]:
        if key in params and params[key]:
            specs.append(f"数量: {params[key]}")
            break

    seen: set[str] = set()
    unique_specs: list[str] = []
    for spec in specs:
        if spec in seen:
            continue
        seen.add(spec)
        unique_specs.append(spec)

    return unique_specs[:6] if unique_specs else ["无详细规格"]


def extract_cost_info(item: dict[str, Any]) -> str:
    """Extract cost/charge prediction info."""
    charge = item.get("chargePredictResult")
    if charge:
        if isinstance(charge, dict):
            total = charge.get("totalCost") or charge.get("cost") or charge.get("amount")
            if total:
                return f"¥{total}"
        return str(charge)
    return "未估算"


def calculate_priority(item: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
    """Calculate priority score and label based on multiple factors."""
    score = 50
    factors: list[str] = []

    created = item.get("createdDate")
    wait_hours = calculate_wait_hours(created, now_ms=now_ms)
    if wait_hours > 72:
        score += 30
        factors.append("等待超3天")
    elif wait_hours > 24:
        score += 15
        factors.append("等待超1天")

    if item.get("sla"):
        score += 20
        factors.append("有SLA")

    if item.get("chargePredictResult"):
        score += 10
        factors.append("有成本预估")

    name = (item.get("name") or "").lower()
    catalog = (item.get("catalogName") or "").lower()
    combined = name + catalog
    high_priority_keywords = ["urgent", "紧急", "生产", "prod", "critical", "重要"]
    if any(keyword in combined for keyword in high_priority_keywords):
        score += 25
        factors.append("关键词标记")

    if score >= 80:
        label = "高"
    elif score >= 60:
        label = "中"
    else:
        label = "低"

    return {"score": score, "label": label, "factors": factors}


def get_approval_step_name(item: dict[str, Any]) -> str:
    """Get current approval step name."""
    activity = item.get("currentActivity") or {}
    step = activity.get("processStep") or {}
    return step.get("name") or "审批中"


def get_approver_info(item: dict[str, Any]) -> str:
    """Extract current approver information."""
    activity = item.get("currentActivity") or {}
    assignments = activity.get("assignments") or []
    approvers: list[str] = []
    for assign in assignments[:2]:
        approver = assign.get("approver") or {}
        name = approver.get("name") or approver.get("loginId") or ""
        if name:
            approvers.append(name)
    return ", ".join(approvers) if approvers else "待分配"


def build_meta(items: list[dict[str, Any]], *, now_ms: int) -> list[dict[str, Any]]:
    """Build the structured approval meta payload."""
    meta: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        activity = item.get("currentActivity") or {}
        meta.append(
            {
                "index": index,
                "id": activity.get("id") or item.get("id") or "",
                "requestId": item.get("id") or "",
                "name": item.get("name") or item.get("requestName") or "",
                "workflowId": item.get("workflowId") or "",
                "catalogName": item.get("catalogName") or "",
                "applicant": item.get("applicant") or "",
                "email": item.get("email") or "",
                "description": item.get("description") or "",
                "createdDate": item.get("createdDate") or "",
                "updatedDate": item.get("updatedDate") or "",
                "waitHours": calculate_wait_hours(item.get("createdDate"), now_ms=now_ms),
                "priority": item["_priority"]["label"],
                "priorityScore": item["_priority"]["score"],
                "priorityFactors": item["_priority"]["factors"],
                "approvalStep": get_approval_step_name(item),
                "currentApprover": get_approver_info(item),
                "costEstimate": extract_cost_info(item),
                "resourceSpecs": extract_resource_specs(item),
                "processInstanceId": activity.get("processInstanceId") or "",
                "taskId": activity.get("taskId") or "",
            }
        )
    return meta


def main(argv: list[str]) -> int:
    """Execute the pending approvals query and render output."""
    days = parse_days_from_argv(argv)
    now_ms = int(time.time() * 1000)
    base_url, auth_token, _headers, _instance = require_config()

    headers = {"Content-Type": "application/json; charset=utf-8", "CloudChef-Authenticate": auth_token}
    url = f"{base_url}/generic-request/current-activity-approval"
    params = build_pending_query_params(now_ms=now_ms, days=days)

    try:
        resp = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as exc:
        print(f"[ERROR] Request failed: {exc}")
        return 1

    items = extract_list(data if isinstance(data, dict) else data)
    total = data.get("totalElements", len(items)) if isinstance(data, dict) else len(items)

    if not items:
        if days is None:
            print("No pending approvals found.")
        else:
            print(f"No pending approvals found in the last {days} days.")
        return 0

    for item in items:
        item["_priority"] = calculate_priority(item, now_ms=now_ms)
    items.sort(key=lambda x: x["_priority"]["score"], reverse=True)

    print("===============================================================")
    print(f"  待审批列表 - 共 {total} 项 (按优先级排序)")
    print("===============================================================\n")

    for index, item in enumerate(items, start=1):
        name = item.get("name") or item.get("requestName") or "N/A"
        workflow_id = item.get("workflowId") or ""
        catalog = item.get("catalogName") or item.get("resourceType") or item.get("type") or "通用请求"
        applicant = item.get("applicant") or item.get("requesterName") or item.get("createdByName") or "N/A"
        email = item.get("email") or ""
        description = item.get("description") or item.get("justification") or ""

        created_str = format_timestamp(item.get("createdDate") or "")
        updated_str = format_timestamp(item.get("updatedDate") or "")
        wait_hours = calculate_wait_hours(item.get("createdDate"), now_ms=now_ms)
        priority = item["_priority"]
        specs = extract_resource_specs(item)
        cost = extract_cost_info(item)
        step_name = get_approval_step_name(item)
        approver = get_approver_info(item)

        print(f"+- [{index}] {priority['label']} -----------------------------------------")
        print(f"|  名称: {name}")
        if workflow_id:
            print(f"|  工单号: {workflow_id}")
        print(f"|  类型: {catalog}")
        print("|")
        print(f"|  申请人: {applicant}" + (f" ({email})" if email else ""))
        if description:
            desc_short = description[:80] + "..." if len(description) > 80 else description
            print(f"|  说明: {desc_short}")
        print("|")
        print(f"|  创建时间: {created_str}")
        print(f"|  更新时间: {updated_str}")
        print(f"|  已等待: {wait_hours}小时")
        print("|")
        print("|  资源规格:")
        for spec in specs:
            print(f"|    - {spec}")
        print(f"|  预估成本: {cost}")
        print("|")
        print(f"|  审批阶段: {step_name}")
        print(f"|  当前审批人: {approver}")
        if priority["factors"]:
            print(f"|  优先因素: {', '.join(priority['factors'])}")
        print("+---------------------------------------------------------------\n")

    high_count = sum(1 for item in items if item["_priority"]["score"] >= 80)
    mid_count = sum(1 for item in items if 60 <= item["_priority"]["score"] < 80)
    low_count = sum(1 for item in items if item["_priority"]["score"] < 60)

    print("===============================================================")
    print(f"  优先级分布: 高 {high_count} | 中 {mid_count} | 低 {low_count}")
    print("===============================================================\n")

    print("##APPROVAL_META_START##")
    print(json.dumps(build_meta(items, now_ms=now_ms), ensure_ascii=False))
    print("##APPROVAL_META_END##")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
