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


def build_alert_meta(alert: Mapping[str, Any], index: int) -> dict[str, Any]:
    """Project SmartCMP alert data into stable English metadata keys."""
    return {
        "index": index,
        "alertId": alert.get("id", ""),
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
        print(f"Found {total} alert(s).")
        print()
        for item in meta:
            print(format_alert_line(item))
    else:
        print("No alerts found.")

    print()
    print("##ALARM_META_START##")
    print(json.dumps(meta, ensure_ascii=False))
    print("##ALARM_META_END##")
    return 0


if __name__ == "__main__":
    sys.exit(main())
