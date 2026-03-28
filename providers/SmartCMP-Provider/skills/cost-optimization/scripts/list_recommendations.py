#!/usr/bin/env python3
"""List SmartCMP cost optimization recommendations."""

import argparse
import json
import sys

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

try:
    from _cost_common import (
        build_pageable_request,
        build_query_request,
        extract_list_payload,
        normalize_money,
        normalize_timestamp,
    )
except ImportError:
    import os

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _cost_common import (  # type: ignore
        build_pageable_request,
        build_query_request,
        extract_list_payload,
        normalize_money,
        normalize_timestamp,
    )


def normalize_violation(item: dict, index: int) -> dict:
    """Normalize a SmartCMP policy violation into stable output fields."""
    task_definition = item.get("taskDefinition") or {}
    return {
        "index": index,
        "violationId": item.get("id", ""),
        "policyId": item.get("policyId", ""),
        "policyName": item.get("policyName", ""),
        "resourceId": item.get("resourceId", ""),
        "resourceName": item.get("resourceName", ""),
        "status": item.get("status", ""),
        "severity": item.get("severity", ""),
        "category": item.get("category", ""),
        "monthlyCost": normalize_money(item.get("monthlyCost")),
        "monthlySaving": normalize_money(item.get("monthlySaving")),
        "savingOperationType": item.get("savingOperationType", ""),
        "fixType": item.get("fixType", ""),
        "taskInstanceId": item.get("taskInstanceId", ""),
        "lastExecuteDate": normalize_timestamp(item.get("lastExecuteDate")),
        "taskDefinitionId": task_definition.get("id", ""),
        "taskDefinitionName": task_definition.get("name", ""),
    }


def format_summary_line(item: dict) -> str:
    """Return a concise human-readable summary line."""
    saving = item["monthlySaving"]
    saving_text = "unknown"
    if saving is not None:
        saving_text = f"{saving:.2f}"
    parts = [
        f"[{item['index']}]",
        item["resourceName"] or "unknown-resource",
        item["policyName"] or "unknown-policy",
        item["status"] or "UNKNOWN",
    ]
    if item["savingOperationType"]:
        parts.append(item["savingOperationType"])
    parts.append(f"saving={saving_text}")
    return " | ".join(parts)


def render_output(items: list[dict]) -> str:
    """Render user-visible summary plus machine-readable metadata."""
    normalized = [normalize_violation(item, index + 1) for index, item in enumerate(items)]
    lines = []
    if normalized:
        lines.append(f"Found {len(normalized)} cost optimization recommendation(s):")
        lines.append("")
        lines.extend(format_summary_line(item) for item in normalized)
    else:
        lines.append("No cost optimization recommendations found.")
    lines.append("")
    lines.append("##COST_RECOMMENDATION_META_START##")
    lines.append(json.dumps(normalized, ensure_ascii=False))
    lines.append("##COST_RECOMMENDATION_META_END##")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="List SmartCMP cost optimization recommendations.")
    parser.add_argument("--status", help="Filter by violation status.")
    parser.add_argument("--severity", action="append", help="Filter by severity.")
    parser.add_argument("--category", help="Filter by category.")
    parser.add_argument("--query", default="", help="Free-text query.")
    parser.add_argument("--page", type=int, default=0, help="Zero-based page index.")
    parser.add_argument("--size", type=int, default=20, help="Page size.")
    args = parser.parse_args()

    base_url, auth_token, _, _ = require_config()
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "CloudChef-Authenticate": auth_token,
    }
    params = {}
    if args.status:
        params["status"] = args.status
    if args.severity:
        params["severity"] = args.severity
    if args.category:
        params["category"] = args.category
    params.update(build_pageable_request(page=args.page, size=args.size))
    params.update(build_query_request(query_value=args.query))

    response = requests.get(
        f"{base_url}/compliance-policies/violations/search",
        headers=headers,
        params=params,
        verify=False,
        timeout=30,
    )
    if response.status_code != 200:
        print(f"[ERROR] HTTP {response.status_code}: {response.text}")
        return 1

    payload = response.json()
    items = extract_list_payload(payload)
    print(render_output(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
