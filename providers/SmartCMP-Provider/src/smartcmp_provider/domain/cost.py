#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Normalize SmartCMP cost values, object operations, and timestamps."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from smartcmp_provider.domain.object_operations import available_operation
from smartcmp_provider.models.object_operations import AvailableOperation

_COMPLETED_REMEDIATION_STATUSES = {"FIXED", "RESOLVED", "SUCCESS", "DONE", "CLOSED"}
_COST_CATEGORY = "COST-OPTIMIZATION"


def is_cost_category(value: Any) -> bool:
    """Return whether a category belongs to the Cost Optimization hierarchy.

    Args:
        value: Raw SmartCMP category value.

    Returns:
        ``True`` only for ``COST-OPTIMIZATION`` or one of its dot-separated
        child categories.
    """

    category = str(value or "").strip().upper()
    return category == _COST_CATEGORY or category.startswith(f"{_COST_CATEGORY}.")


def available_cost_operations(
    item: dict[str, Any],
) -> tuple[AvailableOperation, ...]:
    """Return Cost-only analysis and remediation operations supported by facts.

    Args:
        item: Fresh or list-projected recommendation facts. The category must be
            positively identified as Cost Optimization before any action is exposed.

    Returns:
        Cost analysis plus one justified tracking or remediation operation, or
        an empty tuple for unidentified and non-Cost records.
    """

    if not is_cost_category(item.get("category")):
        return ()
    violation_id = str(item.get("id") or item.get("violationId") or "").strip()
    if not violation_id:
        return ()
    operations = [
        available_operation(
            "analyze",
            "smartcmp.cost.analyze_recommendation",
            arguments={"violation_id": violation_id},
        )
    ]
    for operation_id in available_cost_recommendation_actions(item):
        capability_id = (
            "smartcmp.cost.execution_status"
            if operation_id == "track"
            else "smartcmp.cost.execute"
        )
        operations.append(
            available_operation(
                operation_id,
                capability_id,
                arguments={"violation_id": violation_id},
            )
        )
    return tuple(operations)


def available_cost_recommendation_actions(
    item: dict[str, Any],
) -> tuple[str, ...]:
    """Return follow-up actions justified by SmartCMP remediation facts.

    Args:
        item: Recommendation or analysis facts containing execution, repair, and
            lifecycle fields.

    Returns:
        A single ``track`` or ``remediate`` action when supported, otherwise an
        empty tuple.
    """

    if not is_cost_category(item.get("category")):
        return ()
    if item.get("taskInstanceId"):
        return ("track",)
    executable = bool(
        item.get("fixType")
        or item.get("taskDefinitionName")
        or item.get("taskDefinition")
    )
    status = str(item.get("status") or "").strip().upper()
    if executable and status not in _COMPLETED_REMEDIATION_STATUSES:
        return ("remediate",)
    return ()


def normalize_money(value):
    """Normalize cost-like values to float or None."""
    if value in (None, "", "null"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned.startswith("$") or cleaned.startswith("¥"):
            cleaned = cleaned[1:]
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _resolve_display_timezone(timezone_name: str = ""):
    """Return the current request's IANA timezone, falling back to UTC."""
    timezone_name = str(timezone_name or "").strip()
    if not timezone_name:
        return timezone.utc
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, OSError, ValueError):
        return timezone.utc


def normalize_timestamp(value, *, timezone_name: str = ""):
    """Normalize timestamps to a selected timezone ISO-8601 string or ``None``."""
    if value in (None, "", "null"):
        return None

    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None

    if not isinstance(value, (int, float)):
        return None

    timestamp = float(value)
    if timestamp <= 0:
        return None

    if timestamp > 10_000_000_000:
        timestamp /= 1000.0

    rendered = datetime.fromtimestamp(
        timestamp,
        tz=_resolve_display_timezone(timezone_name),
    ).isoformat()
    return rendered.replace("+00:00", "Z")
