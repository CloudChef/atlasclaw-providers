#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List SmartCMP cost optimization recommendations."""

import argparse
import json
import sys

import requests

try:
    from _common import (
        build_object_open_action,
        build_object_prompt_action,
        build_resource_page_href,
        infer_resource_page_category,
        require_config,
    )
except ImportError:
    import os

    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "scripts"),
    )
    from _common import (  # type: ignore
        build_object_open_action,
        build_object_prompt_action,
        build_resource_page_href,
        infer_resource_page_category,
        require_config,
    )

try:
    from _cost_common import (
        build_pageable_request,
        build_query_request,
        extract_list_payload,
        get_currency_symbol,
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
        get_currency_symbol,
        normalize_money,
        normalize_timestamp,
    )


def normalize_violation(
    item: dict,
    index: int,
    *,
    include_related_policy_count: bool = False,
) -> dict:
    """Normalize a SmartCMP policy violation into stable output fields."""
    task_definition = item.get("taskDefinition") or {}
    normalized = {
        "index": index,
        "violationId": item.get("id", ""),
        "policyId": item.get("policyId", ""),
        "policyName": item.get("policyName", ""),
        "resourceId": item.get("resourceId", ""),
        "resourceName": item.get("resourceName", ""),
        "resourceType": item.get("resourceType", ""),
        "componentType": item.get("componentType", ""),
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
    if include_related_policy_count:
        normalized["relatedPolicyCount"] = max(0, int(item.get("relatedPolicyCount", 0) or 0))
    return normalized


def escape_markdown_cell(value: object) -> str:
    """Render one value safely inside a Markdown table cell."""
    rendered = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    rendered = " ".join(rendered.split())
    return rendered.replace("|", "\\|")


def build_recommendation_object_actions(
    item: dict,
    *,
    base_url: str = "",
) -> list[dict[str, object]]:
    """Build explicit UI actions for one cost optimization recommendation."""
    violation_id = str(item.get("violationId") or "").strip()
    resource_id = str(item.get("resourceId") or "").strip()
    actions: list[dict[str, object]] = []
    if violation_id:
        action = build_object_prompt_action(
            "view_detail",
            label_en="View details",
            label_zh="查看详情",
            prompt_en=f"Analyze cost optimization recommendation {violation_id}",
            prompt_zh=f"分析成本优化建议 {violation_id}",
        )
        if action:
            actions.append(action)

    resource_category = infer_resource_page_category(item)
    if resource_id and base_url and resource_category:
        href = build_resource_page_href(base_url, resource_id, category=resource_category)
        action = build_object_open_action(
            href,
            action_id="open_resource",
            label_en="Open resource",
            label_zh="打开资源",
        )
        if action:
            actions.append(action)
    return actions


def enrich_recommendation_object_metadata(
    item: dict,
    *,
    base_url: str = "",
) -> dict:
    """Attach object identity and action metadata to a normalized recommendation."""
    enriched = dict(item)
    object_id = str(item.get("violationId") or "").strip()
    object_name = str(item.get("policyName") or item.get("resourceName") or object_id).strip()
    enriched.update(
        {
            "object_type": "cost_optimization_recommendation",
            "object_id": object_id,
            "object_name": object_name,
            "object_actions": build_recommendation_object_actions(
                item,
                base_url=base_url,
            ),
        }
    )
    return enriched


def format_summary_line(item: dict, with_related: bool = False, currency: str = "") -> str:
    """Return a concise human-readable summary line."""
    saving = item["monthlySaving"]
    saving_text = "unknown"
    if saving is not None:
        saving_text = f"{currency}{saving:.2f}" if currency else f"{saving:.2f}"
    parts = [
        f"[{item['index']}]",
        item["resourceName"] or "unknown-resource",
        item["policyName"] or "unknown-policy",
        item["status"] or "UNKNOWN",
    ]
    if item["savingOperationType"]:
        parts.append(item["savingOperationType"])
    parts.append(f"saving={saving_text}")
    if with_related and item.get("relatedPolicyCount", 0) > 0:
        parts.append(f"relatedPolicies={item['relatedPolicyCount']}")
    return " | ".join(parts)


def render_recommendation_table(
    items: list[dict],
    *,
    with_related_policies: bool = False,
    currency: str = "",
) -> str:
    """Render cost optimization recommendations as a standard Markdown table."""
    headers = ["#", "Resource", "Policy", "Status", "Operation", "Saving"]
    if with_related_policies:
        headers.append("Related Policies")
    lines = [
        f"Found {len(items)} cost optimization recommendation(s):",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for item in items:
        saving = item["monthlySaving"]
        saving_text = "unknown"
        if saving is not None:
            saving_text = f"{currency}{saving:.2f}" if currency else f"{saving:.2f}"
        row = [
            item["index"],
            item["resourceName"] or "unknown-resource",
            item["policyName"] or "unknown-policy",
            item["status"] or "UNKNOWN",
            item["savingOperationType"] or "N/A",
            saving_text,
        ]
        if with_related_policies:
            row.append(item.get("relatedPolicyCount", 0))
        lines.append("| " + " | ".join(escape_markdown_cell(value) for value in row) + " |")
    return "\n".join(lines)


def render_output(
    items: list[dict],
    with_related_policies: bool = False,
    base_url: str = "",
    auth_token: str = "",
) -> str:
    """Render user-visible summary plus machine-readable metadata."""
    normalized = [
        normalize_violation(
            item,
            index + 1,
            include_related_policy_count=with_related_policies,
        )
        for index, item in enumerate(items)
    ]
    currency = get_currency_symbol(base_url, auth_token) if (base_url or auth_token) else ""
    meta = [
        enrich_recommendation_object_metadata(
            item,
            base_url=base_url,
        )
        for item in normalized
    ]
    lines = []
    if normalized:
        lines.append(
            render_recommendation_table(
                normalized,
                with_related_policies=with_related_policies,
                currency=currency,
            )
        )
    else:
        lines.append("No cost optimization recommendations found.")
    lines.append("")
    lines.append("##COST_RECOMMENDATION_META_START##")
    lines.append(json.dumps(meta, ensure_ascii=False))
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
    parser.add_argument("--with-related-policies", action="store_true",
                        help="Show count of related policies in the same category.")
    args = parser.parse_args()

    base_url, auth_token, headers, _instance = require_config()
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

    # Fetch related policy counts if requested
    if args.with_related_policies and items:
        # Group by category and fetch policy counts
        category_policy_counts = {}
        categories = set(item.get("category") for item in items if item.get("category"))
        for cat in categories:
            try:
                policies_resp = requests.get(
                    f"{base_url}/compliance-policies/search",
                    headers=headers,
                    params={"category": cat, "page": 0, "size": 100},
                    verify=False,
                    timeout=30,
                )
                if policies_resp.status_code == 200:
                    policies_data = policies_resp.json()
                    policies_list = extract_list_payload(policies_data)
                    category_policy_counts[cat] = len(policies_list)
            except Exception:
                pass

        # Update items with related policy counts
        for item in items:
            cat = item.get("category")
            total_policies = category_policy_counts.get(cat, 0)
            # Subtract 1 for the current policy
            item["relatedPolicyCount"] = max(0, total_policies - 1)

    print(
        render_output(
            items,
            args.with_related_policies,
            base_url=base_url,
            auth_token=auth_token,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
