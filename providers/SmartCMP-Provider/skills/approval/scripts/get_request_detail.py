# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Get SmartCMP pending approval/request detail by workflow or related identifiers.

Usage:
  python get_request_detail.py <identifier> [--days N]

Arguments:
  identifier   Workflow ID, approval ID, request ID, task ID, or process instance ID
  --days N     Search approvals updated in the last N days (default: 90)

Output:
  - Human-readable detail summary
  - ##APPROVAL_DETAIL_META_START## ... ##APPROVAL_DETAIL_META_END##
      JSON object with structured info for agent processing
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from typing import Any

import requests

try:
    from _common import require_config
except ImportError:
    import os

    sys.path.insert(
        0,
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "..",
            "shared",
            "scripts",
        ),
    )
    from _common import require_config


BASE_URL, AUTH_TOKEN, HEADERS, _ = require_config()


def _parse_args() -> tuple[str, int]:
    identifier = ""
    days = 90
    args = sys.argv[1:]
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--days" and index + 1 < len(args):
            try:
                days = int(args[index + 1])
            except ValueError:
                pass
            index += 2
            continue
        if not identifier:
            identifier = arg.strip()
        index += 1
    if not identifier:
        print("[ERROR] Missing required identifier argument.")
        sys.exit(1)
    return identifier, max(days, 1)


def _format_timestamp(ts: Any) -> str:
    if isinstance(ts, (int, float)) and ts > 0:
        try:
            return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    return str(ts) if ts else ""


def _calculate_wait_hours(created_ts: Any, now_ms: int) -> float:
    if isinstance(created_ts, (int, float)) and created_ts > 0:
        return round((now_ms - created_ts) / 3600000, 1)
    return 0.0


def _unwrap_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _extract_from_dict(data: dict[str, Any], specs: list[str], prefix: str = "") -> None:
    def _append(label: str, value: Any) -> None:
        normalized = _unwrap_value(value)
        if normalized not in (None, ""):
            specs.append(f"{label}: {normalized}")

    for key in ("cpu", "vcpu", "cpuCount", "cpu_count"):
        if key in data:
            value = _unwrap_value(data[key])
            if value:
                specs.append(f"CPU: {value}核")
                break
    for key in ("memory", "ram", "memorySize", "memory_size"):
        if key in data:
            value = _unwrap_value(data[key])
            if value:
                if isinstance(value, (int, float)) and value >= 1024:
                    specs.append(f"内存: {value / 1024:.1f}GB")
                else:
                    specs.append(f"内存: {value}")
                break
    for key in ("disk", "storage", "diskSize", "disk_size"):
        if key in data:
            _append("存储", data[key])
            break
    if "asset_tag" in data:
        _append("资产标签", data["asset_tag"])
    if "infra_type" in data:
        _append("类型", data["infra_type"])
    if prefix:
        specs.append(f"节点: {prefix}")


def _extract_resource_specs(item: dict[str, Any]) -> list[str]:
    activity = item.get("currentActivity") or {}
    params = activity.get("requestParams") or {}
    specs: list[str] = []
    for value in params.values():
        if isinstance(value, dict):
            _extract_from_dict(value, specs)
    resource_specs = params.get("resourceSpecs") or {}
    if isinstance(resource_specs, dict):
        for node_name, node_spec in resource_specs.items():
            if isinstance(node_spec, dict):
                _extract_from_dict(node_spec, specs, prefix=str(node_name))
    deduped: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        if spec in seen:
            continue
        seen.add(spec)
        deduped.append(spec)
    return deduped[:8] or ["无详细规格"]


def _extract_cost_info(item: dict[str, Any]) -> str:
    charge = item.get("chargePredictResult")
    if isinstance(charge, dict):
        total = charge.get("totalCost") or charge.get("cost") or charge.get("amount")
        if total not in (None, ""):
            return f"¥{total}"
    if charge:
        return str(charge)
    return "未估算"


def _get_approval_step_name(item: dict[str, Any]) -> str:
    activity = item.get("currentActivity") or {}
    step = activity.get("processStep") or {}
    return str(step.get("name") or "审批中")


def _get_approver_info(item: dict[str, Any]) -> str:
    activity = item.get("currentActivity") or {}
    assignments = activity.get("assignments") or []
    approvers: list[str] = []
    for assignment in assignments[:3]:
        approver = assignment.get("approver") or {}
        name = approver.get("name") or approver.get("loginId") or ""
        if name:
            approvers.append(str(name))
    return ", ".join(approvers) if approvers else "待分配"


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
    activity = item.get("currentActivity") or {}
    candidates = [
        activity.get("id"),
        item.get("id"),
        item.get("workflowId"),
        activity.get("taskId"),
        activity.get("processInstanceId"),
    ]
    for candidate in candidates:
        if str(candidate or "").strip().lower() == normalized:
            return True
    return False


def _query_pending_items(days: int) -> list[dict[str, Any]]:
    now_ms = int(time.time() * 1000)
    start_of_today = now_ms - (now_ms % 86400000)
    start_at_min = start_of_today - (days * 86400000)
    start_at_max = now_ms
    url = f"{BASE_URL}/generic-request/current-activity-approval"
    headers = HEADERS
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
        response = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
        response.raise_for_status()
        items = _extract_items(response.json())
        if not items:
            break
        all_items.extend(items)
        if len(items) < 50:
            break
    return all_items


def main() -> None:
    identifier, days = _parse_args()
    try:
        items = _query_pending_items(days)
    except requests.exceptions.RequestException as error:
        print(f"[ERROR] Request failed: {error}")
        sys.exit(1)

    matched = next((item for item in items if _matches_identifier(item, identifier)), None)
    if matched is None:
        print(f"[ERROR] No pending SmartCMP approval matched identifier: {identifier}")
        sys.exit(1)

    now_ms = int(time.time() * 1000)
    activity = matched.get("currentActivity") or {}
    name = matched.get("name") or matched.get("requestName") or "N/A"
    workflow_id = matched.get("workflowId") or ""
    catalog = matched.get("catalogName") or matched.get("resourceType") or matched.get("type") or "通用请求"
    applicant = matched.get("applicant") or matched.get("requesterName") or matched.get("createdByName") or "N/A"
    email = matched.get("email") or ""
    description = matched.get("description") or matched.get("justification") or ""
    created_date = matched.get("createdDate") or ""
    updated_date = matched.get("updatedDate") or ""
    wait_hours = _calculate_wait_hours(created_date, now_ms)
    resource_specs = _extract_resource_specs(matched)
    cost_estimate = _extract_cost_info(matched)
    approval_step = _get_approval_step_name(matched)
    current_approver = _get_approver_info(matched)

    print("===============================================================")
    print(f"  CMP 工单详情: {workflow_id or identifier}")
    print("===============================================================")
    print(f"名称: {name}")
    print(f"类型: {catalog}")
    print(f"申请人: {applicant}" + (f" ({email})" if email else ""))
    print(f"审批阶段: {approval_step}")
    print(f"当前审批人: {current_approver}")
    print(f"创建时间: {_format_timestamp(created_date)}")
    print(f"更新时间: {_format_timestamp(updated_date)}")
    print(f"已等待: {wait_hours} 小时")
    print(f"预估成本: {cost_estimate}")
    print("资源规格:")
    for spec in resource_specs:
        print(f"- {spec}")
    if description:
        print(f"说明: {description}")
    print("")
    print("流程标识:")
    print(f"- approvalId: {activity.get('id') or matched.get('id') or ''}")
    print(f"- requestId: {matched.get('id') or ''}")
    print(f"- workflowId: {workflow_id}")
    print(f"- processInstanceId: {activity.get('processInstanceId') or ''}")
    print(f"- taskId: {activity.get('taskId') or ''}")

    meta = {
        "approvalId": activity.get("id") or matched.get("id") or "",
        "requestId": matched.get("id") or "",
        "workflowId": workflow_id,
        "taskId": activity.get("taskId") or "",
        "processInstanceId": activity.get("processInstanceId") or "",
        "name": name,
        "catalogName": catalog,
        "applicant": applicant,
        "email": email,
        "description": description,
        "createdDate": created_date,
        "updatedDate": updated_date,
        "waitHours": wait_hours,
        "approvalStep": approval_step,
        "currentApprover": current_approver,
        "costEstimate": cost_estimate,
        "resourceSpecs": resource_specs,
    }
    print("##APPROVAL_DETAIL_META_START##")
    print(json.dumps(meta, ensure_ascii=False))
    print("##APPROVAL_DETAIL_META_END##")


if __name__ == "__main__":
    main()
