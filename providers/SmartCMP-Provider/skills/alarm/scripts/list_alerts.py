# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List SmartCMP alarm alerts with human and machine-readable output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _alarm_common import (
    DEFAULT_PAGE,
    DEFAULT_SIZE,
    build_list_params,
    extract_items,
    get_json,
    normalize_timestamp,
)
from _common import build_object_prompt_action


def positive_int(value: str) -> int:
    """Parse a strictly positive integer argument."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for alert listing."""
    parser = argparse.ArgumentParser(description="List SmartCMP alarm alerts.")
    parser.add_argument("--status", dest="statuses", action="append", help="Alert status filter.")
    parser.add_argument("--days", type=positive_int, default=7, help="Look back window in days.")
    parser.add_argument("--level", type=int, help="Alert level filter.")
    parser.add_argument("--deployment-id", help="Deployment identifier filter.")
    parser.add_argument("--entity-instance-id", help="Entity instance identifier filter.")
    parser.add_argument("--node-instance-id", help="Node instance identifier filter.")
    parser.add_argument("--alarm-type", help="Alarm type filter.")
    parser.add_argument("--alarm-category", dest="alarm_categories", action="append", help="Alarm category filter.")
    parser.add_argument("--query", help="Optional keyword filter.")
    parser.add_argument("--page", type=positive_int, default=DEFAULT_PAGE, help="Result page number.")
    parser.add_argument("--size", type=positive_int, default=DEFAULT_SIZE, help="Page size.")
    return parser.parse_args(argv)


def normalize_entity_ids(value: Any) -> list[str]:
    """Normalize entity identifiers to a stable string list."""
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _alert_object_name(alert: Mapping[str, Any]) -> str:
    """Pick a stable, human-visible alert object label."""
    for key in ("alarmPolicyName", "alarmActivityName", "resourceExternalName", "entityInstanceName", "id"):
        value = alert.get(key)
        if value:
            return str(value)
    return "unknown-alert"


def build_alert_object_actions(alert_id: str) -> list[dict[str, object]]:
    """Build explicit UI actions for one SmartCMP alert row."""
    normalized_alert_id = str(alert_id or "").strip()
    if not normalized_alert_id:
        return []
    action = build_object_prompt_action(
        "view_detail",
        label_en="View details",
        label_zh="查看详情",
        prompt_en=f"Analyze alert {normalized_alert_id}",
        prompt_zh=f"分析告警 {normalized_alert_id}",
    )
    return [action] if action else []


def build_alert_meta(alert: Mapping[str, Any], index: int) -> dict[str, Any]:
    """Project SmartCMP alert data into stable English metadata keys."""
    alert_id = str(alert.get("id", "") or "")
    object_name = _alert_object_name(alert)
    return {
        "index": index,
        "object_type": "alarm_alert",
        "object_id": alert_id,
        "object_name": object_name,
        "object_actions": build_alert_object_actions(alert_id),
        "alertId": alert_id,
        "alarmActivityId": alert.get("alarmActivityId", ""),
        "alarmActivityName": alert.get("alarmActivityName", ""),
        "alarmPolicyId": alert.get("alarmPolicyId", ""),
        "alarmPolicyName": alert.get("alarmPolicyName", ""),
        "status": alert.get("status", ""),
        "level": alert.get("level"),
        "triggerAt": normalize_timestamp(alert.get("triggerAt")),
        "lastTriggerAt": normalize_timestamp(alert.get("lastTriggerAt")),
        "triggerCount": alert.get("triggerCount", 0),
        "deploymentId": alert.get("deploymentId", ""),
        "deploymentName": alert.get("deploymentName", ""),
        "entityInstanceId": normalize_entity_ids(alert.get("entityInstanceId")),
        "entityInstanceName": alert.get("entityInstanceName", ""),
        "nodeInstanceId": alert.get("nodeInstanceId", ""),
        "resourceExternalId": alert.get("resourceExternalId", ""),
        "resourceExternalName": alert.get("resourceExternalName", ""),
        "metricName": alert.get("metricName", ""),
        "subject": alert.get("subject", ""),
        "operationNum": alert.get("operationNum", 0),
        "notificationNum": alert.get("notificationNum", 0),
    }


def build_query_params(args: argparse.Namespace) -> dict[str, Any]:
    """Translate parsed arguments into SmartCMP query parameters."""
    return build_list_params(
        page=args.page,
        size=args.size,
        statuses=args.statuses,
        days=args.days,
        level=args.level,
        deployment_id=args.deployment_id or "",
        entity_instance_id=args.entity_instance_id or "",
        node_instance_id=args.node_instance_id or "",
        alarm_type=args.alarm_type or "",
        alarm_categories=args.alarm_categories,
        queryValue=args.query or "",
    )


def select_resource_name(meta: Mapping[str, Any]) -> str:
    """Pick the best available resource label for human output."""
    for key in ("resourceExternalName", "entityInstanceName", "deploymentName", "nodeInstanceId", "alertId"):
        value = meta.get(key)
        if value:
            return str(value)
    return "unknown"


def format_alert_line(meta: Mapping[str, Any]) -> str:
    """Render one concise alert summary line."""
    policy_name = meta.get("alarmPolicyName") or meta.get("alarmActivityName") or meta.get("alertId") or "unknown"
    return (
        f"[{meta['index']}] {policy_name} | "
        f"status={meta.get('status', '')} | "
        f"level={meta.get('level', '')} | "
        f"resource={select_resource_name(meta)}"
    )


def escape_markdown_cell(value: object) -> str:
    """Render one value safely inside a Markdown table cell."""
    rendered = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    rendered = " ".join(rendered.split())
    return rendered.replace("|", "\\|")


def render_alert_table(items: list[Mapping[str, Any]], total: int) -> str:
    """Render SmartCMP alert list output as a standard Markdown table."""
    headers = ["#", "Policy", "Status", "Level", "Resource"]
    lines = [
        f"Found {total} alert(s):",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for item in items:
        row = [
            item.get("index", ""),
            item.get("alarmPolicyName") or item.get("alarmActivityName") or item.get("alertId") or "unknown",
            item.get("status", ""),
            item.get("level", ""),
            select_resource_name(item),
        ]
        lines.append("| " + " | ".join(escape_markdown_cell(value) for value in row) + " |")
    return "\n".join(lines)


def extract_total(payload: Any, items: Iterable[Any]) -> int:
    """Extract the total count when available, otherwise fall back to item count."""
    if isinstance(payload, Mapping):
        total = payload.get("totalElements")
        if isinstance(total, int):
            return total
    return len(list(items))


def main(argv: list[str] | None = None) -> int:
    """Entry point for alert listing."""
    args = parse_args(argv)
    params = build_query_params(args)
    try:
        payload = get_json("/alarm-alert", params=params)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1

    items = extract_items(payload)
    meta = [build_alert_meta(item, index) for index, item in enumerate(items, start=1)]
    total = extract_total(payload, meta)

    if meta:
        print(render_alert_table(meta, total))
    else:
        print("No alerts found.")

    print()
    print("##ALARM_META_START##")
    print(json.dumps(meta, ensure_ascii=False))
    print("##ALARM_META_END##")
    return 0


if __name__ == "__main__":
    sys.exit(main())
