# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Shared helpers for SmartCMP alarm retrieval, analysis, and operations."""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Mapping

from smartcmp_provider.domain.object_operations import available_operation
from smartcmp_provider.domain.time import normalize_timestamp
from smartcmp_provider.models.object_operations import AvailableOperation


ACTION_STATUS_MAP = {
    "mute": "ALERT_MUTED",
    "resolve": "ALERT_RESOLVED",
    "reopen": "ALERT_FIRING",
}
ALERT_STATUS_OPERATIONS = {
    "ALERT_FIRING": ("mute", "resolve"),
    "ALERT_MUTED": ("resolve", "reopen"),
    "ALERT_RESOLVED": ("reopen",),
}
DEFAULT_PAGE = 1
DEFAULT_SIZE = 20
DEFAULT_SORT = ""
ONE_DAY_MS = 86_400_000


def normalize_action(action: str) -> str:
    """Normalize an English action and validate it."""
    normalized = (action or "").strip().lower()
    if normalized not in ACTION_STATUS_MAP:
        valid_actions = ", ".join(sorted(ACTION_STATUS_MAP))
        raise ValueError(f"Unsupported action '{action}'. Expected one of: {valid_actions}.")
    return normalized


def map_action_to_status(action: str) -> str:
    """Map an English action to the SmartCMP alert status."""
    return ACTION_STATUS_MAP[normalize_action(action)]


def available_alert_operations(
    alert: Mapping[str, Any],
) -> tuple[AvailableOperation, ...]:
    """Return analysis and state-valid mutations for one exact alert."""

    alert_id = str(alert.get("id") or "").strip()
    if not alert_id:
        return ()
    operations = [
        available_operation(
            "analyze",
            "smartcmp.alarms.analyze",
            arguments={"alert_id": alert_id},
        )
    ]
    operations.extend(
        available_operation(
            operation,
            "smartcmp.alarms.operate",
            arguments={"alert_ids": [alert_id], "action": operation},
        )
        for operation in allowed_alert_operations(alert.get("status"))
    )
    return tuple(operations)


def allowed_alert_operations(status: Any) -> tuple[str, ...]:
    """Return the SmartCMP operations valid for one observed alert status."""

    normalized = str(status or "").strip().upper()
    return ALERT_STATUS_OPERATIONS.get(normalized, ())


def build_list_params(
    page: int = DEFAULT_PAGE,
    size: int = DEFAULT_SIZE,
    sort: str = DEFAULT_SORT,
    statuses: Any = None,
    days: int | None = None,
    level: int | None = None,
    deployment_id: str = "",
    entity_instance_id: str = "",
    node_instance_id: str = "",
    target_entity_id: str = "",
    alarm_type: str = "",
    alarm_categories: Any = None,
    business_group_ids: Any = None,
    group_ids: Any = None,
    now_ms: int | None = None,
    **filters: Any,
) -> Dict[str, Any]:
    """Build query parameters, omitting blank optional values."""
    params: Dict[str, Any] = {"page": page, "size": size}
    if sort:
        params["sort"] = sort

    if days is not None and int(days) > 0:
        end_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        params["triggerAtMin"] = end_ms - (int(days) * ONE_DAY_MS)
        params["triggerAtMax"] = end_ms

    status_list = normalize_list_argument(statuses)
    if status_list:
        params["status"] = status_list

    category_list = normalize_list_argument(alarm_categories)
    if category_list:
        params["alarmCategory"] = category_list

    business_group_list = normalize_list_argument(business_group_ids)
    if business_group_list:
        params["businessGroupIds"] = business_group_list

    group_list = normalize_list_argument(group_ids)
    if group_list:
        params["groupIds"] = group_list

    if level is not None:
        params["level"] = int(level)
    if deployment_id:
        params["deploymentId"] = deployment_id
    if entity_instance_id:
        params["entityInstanceId"] = entity_instance_id
    if node_instance_id:
        params["nodeInstanceId"] = node_instance_id
    if target_entity_id:
        params["targetEntityId"] = target_entity_id
    if alarm_type:
        params["alarmType"] = alarm_type

    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        params[key] = value
    return params


def normalize_list_argument(value: Any) -> List[str]:
    """Normalize list-like filter values into a compact string list."""
    if value in (None, ""):
        return []

    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, Iterable):
        parts = []
        for item in value:
            if item in (None, ""):
                continue
            parts.extend(str(item).split(","))
    else:
        parts = [str(value)]

    normalized = []
    for part in parts:
        stripped = str(part).strip()
        if stripped:
            normalized.append(stripped)
    return normalized


def find_alert_by_id(items: Iterable[Mapping[str, Any]], alert_id: str) -> Dict[str, Any]:
    """Return the first alert whose id matches the provided alert_id."""
    for item in items:
        if item.get("id") == alert_id:
            return dict(item)
    return {}
