#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Query SmartCMP service request status by user-facing Request ID.

Usage:
  python status.py RES20260501000095
  python status.py <internal-request-id>

Output:
  - Human-readable request status summary
  - ##REQUEST_STATUS_META_START## ... ##REQUEST_STATUS_META_END##
      JSON object with structured status info for agent processing
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

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


MATCH_FIELDS = (
    "workflowId",
    "requestNo",
    "requestNumber",
    "customizedId",
    "id",
)

APPROVAL_PENDING_STATES = {"APPROVAL_PENDING"}
APPROVAL_REJECTED_STATES = {"APPROVAL_REJECTED", "APPROVAL_RETREATED"}
APPROVAL_PASSED_STATES = {"STARTED", "TASK_RUNNING", "WAIT_EXECUTE", "FINISHED"}
INITIAL_OR_FAILED_STATES = {
    "INITIALING",
    "INITIALING_FAILED",
    "FAILED",
    "CANCELED",
    "CANCELLED",
    "TIMEOUT_CLOSED",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query SmartCMP request status.")
    parser.add_argument("request_id", help="SmartCMP Request ID, e.g. RES20260501000095 or TIC20260316000001.")
    return parser.parse_args(argv)


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def canonical_state(value: Any) -> str:
    return normalize_text(value).upper().replace("-", "_")


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("content", "data", "items", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("content", "items", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def format_timestamp(value: Any) -> str:
    if isinstance(value, (int, float)) and value > 0:
        try:
            return datetime.fromtimestamp(value / 1000).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(value)
    return normalize_text(value)


def iter_match_values(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in MATCH_FIELDS:
        candidate = normalize_text(item.get(field))
        if candidate:
            values.append(candidate)
    return values


def matches_request_id(item: dict[str, Any], request_id: str) -> bool:
    normalized = normalize_text(request_id).lower()
    return any(value.lower() == normalized for value in iter_match_values(item))


def display_request_id(item: dict[str, Any], fallback: str) -> str:
    for field in ("workflowId", "requestNo", "requestNumber", "customizedId"):
        candidate = normalize_text(item.get(field))
        if candidate:
            return candidate
    return normalize_text(fallback)


def internal_request_id(item: dict[str, Any], fallback: str = "") -> str:
    return normalize_text(item.get("id")) or normalize_text(fallback)


def current_step_name(item: dict[str, Any]) -> str:
    activity = item.get("currentActivity")
    if isinstance(activity, dict):
        process_step = activity.get("processStep")
        if isinstance(process_step, dict):
            candidate = normalize_text(process_step.get("name"))
            if candidate:
                return candidate
        for field in ("name", "activityName", "taskName"):
            candidate = normalize_text(activity.get(field))
            if candidate:
                return candidate
    task_node = item.get("taskNode")
    if isinstance(task_node, dict):
        return normalize_text(task_node.get("name"))
    return ""


def current_approver(item: dict[str, Any]) -> str:
    activity = item.get("currentActivity")
    if isinstance(activity, dict):
        assignments = activity.get("assignments")
        if isinstance(assignments, list):
            names: list[str] = []
            for assignment in assignments[:3]:
                if not isinstance(assignment, dict):
                    continue
                approver = assignment.get("approver")
                if isinstance(approver, dict):
                    name = normalize_text(approver.get("name") or approver.get("loginId"))
                    if name:
                        names.append(name)
                        continue
                name = normalize_text(assignment.get("name") or assignment.get("loginId") or assignment.get("assigneeName"))
                if name:
                    names.append(name)
            if names:
                return ", ".join(names)
    current = item.get("currentAssignee")
    if isinstance(current, dict):
        return normalize_text(current.get("name") or current.get("loginId"))
    return normalize_text(item.get("currentAssignee") or item.get("assigneeName") or item.get("assigneeId"))


def error_message(item: dict[str, Any], status_category: str) -> str:
    explicit_error = normalize_text(
        item.get("errMsg")
        or item.get("errorMessage")
        or item.get("closeNotes")
        or item.get("resolutionNotes")
    )
    if explicit_error:
        return explicit_error
    if status_category in {"approval_rejected", "initial_or_failed"}:
        return normalize_text(item.get("message"))
    return ""


def classify_status(state: Any) -> tuple[str, bool | None]:
    normalized = canonical_state(state)
    if normalized in APPROVAL_PENDING_STATES:
        return "approval_pending", False
    if normalized in APPROVAL_REJECTED_STATES:
        return "approval_rejected", False
    if normalized in APPROVAL_PASSED_STATES:
        return "approval_passed", True
    if normalized in INITIAL_OR_FAILED_STATES:
        return "initial_or_failed", None
    if normalized == "ON_HOLD":
        return "on_hold", None
    if normalized == "ARCHIVED":
        return "archived", None
    if normalized == "RE_APPLY":
        return "re_apply", False
    return "unknown", None


def fetch_json(url: str, headers: dict[str, str], *, params: dict[str, Any] | None = None) -> tuple[dict[str, Any] | list[Any] | None, str]:
    try:
        response = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
    except requests.exceptions.RequestException as exc:
        return None, str(exc)
    if response.status_code != 200:
        return None, f"HTTP {response.status_code}: {(response.text or '').strip()}"
    try:
        payload = response.json()
    except (ValueError, TypeError):
        return None, f"Invalid JSON response: {response.text}"
    if not isinstance(payload, (dict, list)):
        return None, f"Unexpected response payload: {payload}"
    return payload, ""


def search_requests(base_url: str, headers: dict[str, str], request_id: str) -> tuple[list[dict[str, Any]], str]:
    params = {
        "page": 1,
        "size": 20,
        "sort": "updatedDate,desc",
        "queryValue": request_id,
        "states": "",
    }
    payload, error = fetch_json(f"{base_url}/generic-request/search", headers, params=params)
    if error:
        return [], error
    return extract_items(payload), ""


def fetch_request_detail(base_url: str, headers: dict[str, str], request_id: str) -> tuple[dict[str, Any] | None, str]:
    payload, error = fetch_json(f"{base_url}/generic-request/{request_id}", headers)
    if error:
        return None, error
    if not isinstance(payload, dict):
        return None, f"Unexpected detail payload: {payload}"
    return payload, ""


def resolve_request(base_url: str, headers: dict[str, str], request_id: str) -> tuple[dict[str, Any] | None, str]:
    search_items, search_error = search_requests(base_url, headers, request_id)
    matched = next((item for item in search_items if matches_request_id(item, request_id)), None)
    if matched is not None:
        detail_id = internal_request_id(matched, request_id)
        detail, detail_error = fetch_request_detail(base_url, headers, detail_id)
        if detail is not None:
            return detail, ""
        return None, f"Matched Request ID {request_id}, but detail lookup failed for {detail_id}: {detail_error}"

    detail, detail_error = fetch_request_detail(base_url, headers, request_id)
    if detail is not None:
        return detail, ""

    errors = []
    if search_error:
        errors.append(f"search failed: {search_error}")
    if detail_error:
        errors.append(f"direct detail failed: {detail_error}")
    suffix = f" ({'; '.join(errors)})" if errors else ""
    return None, f"No SmartCMP request matched Request ID: {request_id}{suffix}"


def build_status_meta(item: dict[str, Any], requested_id: str) -> dict[str, Any]:
    state = canonical_state(item.get("state"))
    category, approval_passed = classify_status(state)
    created_date = item.get("createdDate") or item.get("actualStartDate") or item.get("plannedStartDate")
    updated_date = item.get("updatedDate") or item.get("completedDate") or item.get("actualEndDate")
    return {
        "requestId": display_request_id(item, requested_id),
        "internalRequestId": internal_request_id(item),
        "name": normalize_text(item.get("name") or item.get("requestName")),
        "catalogName": normalize_text(item.get("catalogName") or item.get("currentCatalogName") or item.get("currentCatalogNameZh")),
        "state": state,
        "provisionState": normalize_text(item.get("provisionState")),
        "statusCategory": category,
        "approvalPassed": approval_passed,
        "currentStep": current_step_name(item),
        "currentApprover": current_approver(item),
        "error": error_message(item, category),
        "createdDate": created_date,
        "createdAt": format_timestamp(created_date),
        "updatedDate": updated_date,
        "updatedAt": format_timestamp(updated_date),
    }


def render_status(meta: dict[str, Any]) -> str:
    lines = [
        "===============================================================",
        f"  CMP Request Status: {meta.get('requestId') or meta.get('internalRequestId') or 'N/A'}",
        "===============================================================",
        f"Request ID: {meta.get('requestId') or 'N/A'}",
    ]
    internal_id = normalize_text(meta.get("internalRequestId"))
    if internal_id and internal_id != normalize_text(meta.get("requestId")):
        lines.append(f"Internal ID: {internal_id}")
    if meta.get("name"):
        lines.append(f"Name: {meta['name']}")
    if meta.get("catalogName"):
        lines.append(f"Catalog: {meta['catalogName']}")
    lines.append(f"State: {meta.get('state') or 'UNKNOWN'}")
    if meta.get("provisionState"):
        lines.append(f"Provision State: {meta['provisionState']}")
    lines.append(f"Status Category: {meta.get('statusCategory') or 'unknown'}")
    approval_passed = meta.get("approvalPassed")
    approval_passed_text = "unknown" if approval_passed is None else str(bool(approval_passed)).lower()
    lines.append(f"Approval Passed: {approval_passed_text}")
    if meta.get("currentStep"):
        lines.append(f"Current Step: {meta['currentStep']}")
    if meta.get("currentApprover"):
        lines.append(f"Current Assignee: {meta['currentApprover']}")
    if meta.get("createdAt"):
        lines.append(f"Created At: {meta['createdAt']}")
    if meta.get("updatedAt"):
        lines.append(f"Updated At: {meta['updatedAt']}")
    if meta.get("error"):
        lines.append(f"Error: {meta['error']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    request_id = normalize_text(args.request_id)
    if not request_id:
        print("[ERROR] Missing required request_id argument.")
        return 1

    base_url, _auth_token, headers, _instance = require_config()
    detail, error = resolve_request(base_url, headers, request_id)
    if detail is None:
        print(f"[ERROR] {error}")
        return 1

    meta = build_status_meta(detail, request_id)
    print(render_status(meta))
    if error:
        print(f"Note: {error}")

    print("##REQUEST_STATUS_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False), file=sys.stderr)
    print("##REQUEST_STATUS_META_END##", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
