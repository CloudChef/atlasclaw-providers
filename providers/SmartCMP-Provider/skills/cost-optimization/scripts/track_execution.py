#!/usr/bin/env python3
"""Track SmartCMP-native cost optimization execution status."""

from __future__ import annotations

import argparse
import json
import sys

import requests
from requests import RequestException

try:
    from _common import require_config
except ImportError:
    import os

    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "scripts"),
    )
    from _common import require_config

try:
    from _cost_common import build_pageable_request, build_query_request, extract_list_payload, normalize_timestamp
except ImportError:
    import os

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _cost_common import (  # type: ignore
        build_pageable_request,
        build_query_request,
        extract_list_payload,
        normalize_timestamp,
    )


STATUS_ALIASES = {
    "RUNNING": "EXECUTING",
    "PROCESSING": "EXECUTING",
    "IN_PROGRESS": "EXECUTING",
    "PENDING": "EXECUTING",
}


def normalize_status(value) -> str:
    """Normalize status values into stable uppercase labels."""
    if value in (None, "", "null"):
        return "UNKNOWN"

    status = str(value).strip().upper()
    if not status:
        return "UNKNOWN"
    return STATUS_ALIASES.get(status, status)


def normalize_violation_instance(item: dict) -> dict:
    """Normalize a violation-instance row into a stable execution record."""
    execution_id = (
        item.get("executionId")
        or item.get("taskInstanceId")
        or item.get("taskId")
        or item.get("id")
        or ""
    )
    return {
        "source": "violation-instance",
        "recordId": item.get("id", ""),
        "violationId": item.get("violationId", ""),
        "executionId": execution_id,
        "policyId": item.get("policyId", ""),
        "policyName": item.get("policyName", ""),
        "resourceId": item.get("resourceId", ""),
        "resourceName": item.get("resourceName", ""),
        "status": normalize_status(item.get("status")),
        "message": item.get("violationMessage", "") or item.get("message", "") or "",
        "createdAt": normalize_timestamp(item.get("createdTime") or item.get("createTime")),
        "updatedAt": normalize_timestamp(item.get("updatedTime") or item.get("modifyTime")),
    }


def normalize_resource_execution(item: dict) -> dict:
    """Normalize a resource-execution row into a stable execution record."""
    execution_id = (
        item.get("executionId")
        or item.get("taskInstanceId")
        or item.get("id")
        or ""
    )
    return {
        "source": "resource-execution",
        "recordId": item.get("id", ""),
        "violationId": item.get("policyViolationId", "") or item.get("violationId", ""),
        "executionId": execution_id,
        "resourceName": item.get("resourceName", ""),
        "resourceId": item.get("resourceId", ""),
        "status": normalize_status(item.get("status")),
        "message": item.get("errMsg", "") or item.get("message", "") or "",
        "createdAt": normalize_timestamp(item.get("createTime") or item.get("createdTime")),
        "updatedAt": normalize_timestamp(item.get("updateTime") or item.get("modifiedTime")),
    }


def collect_execution_ids(violation_instances: list[dict]) -> list[str]:
    """Collect unique execution identifiers in discovery order."""
    execution_ids = []
    seen = set()
    for item in violation_instances:
        execution_id = str(
            item.get("executionId")
            or item.get("taskInstanceId")
            or item.get("taskId")
            or item.get("id")
            or ""
        ).strip()
        if not execution_id or execution_id in seen:
            continue
        seen.add(execution_id)
        execution_ids.append(execution_id)
    return execution_ids


def collapse_overall_status(records: list[dict]) -> str:
    """Collapse record-level states into one overall execution status."""
    statuses = {record.get("status", "UNKNOWN") for record in records if record.get("status")}
    statuses.discard("UNKNOWN")

    if not records:
        return "FAILED"
    if not statuses:
        return "PARTIAL"
    if statuses == {"SUCCESS"}:
        return "SUCCESS"
    if statuses == {"FAILED"}:
        return "FAILED"
    if statuses == {"EXECUTING"}:
        return "EXECUTING"
    return "PARTIAL"


def build_tracking_summary(
    violation_id: str,
    violation_instances: list[dict],
    resource_executions: list[dict],
    resource_executions_available: bool,
    warnings: list[str] | None = None,
) -> dict:
    """Build the normalized execution tracking summary."""
    records = violation_instances + resource_executions
    failure_messages = []
    seen_messages = set()
    for record in records:
        if record.get("status") != "FAILED":
            continue
        message = (record.get("message") or "").strip()
        if not message:
            continue
        key = (record.get("source", ""), record.get("executionId", ""), message)
        if key in seen_messages:
            continue
        seen_messages.add(key)
        failure_messages.append(
            {
                "source": record.get("source", ""),
                "executionId": record.get("executionId", ""),
                "recordId": record.get("recordId", ""),
                "message": message,
            }
        )

    status_counts = {}
    for record in records:
        status = record.get("status", "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1

    summary = {
        "violationId": violation_id,
        "overallStatus": collapse_overall_status(records),
        "sourceAvailability": {
            "violationInstances": True,
            "resourceExecutions": resource_executions_available,
        },
        "trackedExecutionIds": collect_execution_ids(violation_instances),
        "recordCounts": {
            "violationInstances": len(violation_instances),
            "resourceExecutions": len(resource_executions),
            "total": len(records),
        },
        "statusCounts": status_counts,
        "violationInstances": violation_instances,
        "resourceExecutions": resource_executions,
        "records": records,
        "failureMessages": failure_messages,
        "warnings": warnings or [],
    }
    return summary


def render_tracking_output(summary: dict) -> str:
    """Render a human-readable summary plus the structured tracking block."""
    lines = [
        f"Violation {summary['violationId']}: {summary['overallStatus']}",
        f"Execution IDs: {', '.join(summary['trackedExecutionIds']) if summary['trackedExecutionIds'] else 'none'}",
        (
            "Records: "
            f"{summary['recordCounts']['total']} "
            f"(violation instances={summary['recordCounts']['violationInstances']}, "
            f"resource executions={summary['recordCounts']['resourceExecutions']})"
        ),
    ]

    if summary["failureMessages"]:
        lines.append("Failure messages:")
        for item in summary["failureMessages"]:
            source = item.get("source") or "unknown-source"
            execution_id = item.get("executionId") or "unknown-execution"
            lines.append(f"- {source} {execution_id}: {item.get('message', '')}")
    else:
        lines.append("Failure messages: none")

    if summary["warnings"]:
        lines.append("Warnings:")
        for warning in summary["warnings"]:
            lines.append(f"- {warning}")

    lines.extend(
        [
            "",
            "##COST_EXECUTION_TRACK_START##",
            json.dumps(summary, ensure_ascii=False),
            "##COST_EXECUTION_TRACK_END##",
        ]
    )
    return "\n".join(lines)


def fetch_tracking_items(base_url: str, headers: dict, params: dict, endpoint: str):
    """Fetch and normalize a paged SmartCMP list response."""
    try:
        response = requests.get(
            f"{base_url}{endpoint}",
            headers=headers,
            params=params,
            verify=False,
            timeout=30,
        )
    except RequestException as exc:
        return None, False, f"{endpoint} request failed: {exc}"

    if response.status_code != 200:
        return None, False, f"{endpoint} returned HTTP {response.status_code}: {response.text}"

    try:
        payload = response.json()
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return None, False, f"{endpoint} returned invalid JSON: {exc}"

    return extract_list_payload(payload), True, None


def fetch_resource_executions(
    base_url: str,
    headers: dict,
    execution_ids: list[str],
) -> tuple[list[dict], bool, list[str]]:
    """Fetch resource-execution details for each discovered execution id."""
    if not execution_ids:
        return [], True, []

    normalized_items: list[dict] = []
    warnings: list[str] = []
    available = True
    seen_records = set()

    for execution_id in execution_ids:
        params = {
            "executionId": execution_id,
        }
        params.update(build_pageable_request(page=0, size=100))
        params.update(build_query_request(query_value=execution_id))
        items, ok, warning = fetch_tracking_items(
            base_url,
            headers,
            params,
            "/compliance-policies/resource-executions/search",
        )
        if not ok:
            available = False
            if warning:
                warnings.append(warning)
            continue

        for item in items or []:
            normalized = normalize_resource_execution(item)
            record_key = (
                normalized.get("source", ""),
                normalized.get("recordId", ""),
                normalized.get("executionId", ""),
                normalized.get("status", ""),
                normalized.get("message", ""),
            )
            if record_key in seen_records:
                continue
            seen_records.add(record_key)
            normalized_items.append(normalized)

    return normalized_items, available, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Track SmartCMP-native execution state for a cost optimization fix.")
    parser.add_argument("--id", required=True, help="Violation identifier.")
    args = parser.parse_args()

    violation_id = (args.id or "").strip()
    if not violation_id:
        print("[ERROR] --id must not be empty.")
        return 1

    base_url, auth_token, headers, _ = require_config()

    violation_params = {
        "violationId": violation_id,
    }
    violation_params.update(build_pageable_request(page=0, size=100))
    violation_params.update(build_query_request(query_value=violation_id))

    violation_items, ok, warning = fetch_tracking_items(
        base_url,
        headers,
        violation_params,
        "/compliance-policies/violation-instances/search",
    )
    if not ok:
        print(f"[ERROR] {warning}")
        return 1

    normalized_violation_instances = [normalize_violation_instance(item) for item in violation_items or []]
    execution_ids = collect_execution_ids(normalized_violation_instances)
    resource_executions, resource_available, resource_warnings = fetch_resource_executions(
        base_url,
        headers,
        execution_ids,
    )
    warnings = []
    if warning:
        warnings.append(warning)
    warnings.extend(resource_warnings)
    if not execution_ids:
        warnings.append("No execution IDs were returned from violation instances; resource executions were not queried.")

    summary = build_tracking_summary(
        violation_id=violation_id,
        violation_instances=normalized_violation_instances,
        resource_executions=resource_executions,
        resource_executions_available=resource_available,
        warnings=warnings,
    )
    print(render_tracking_output(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
