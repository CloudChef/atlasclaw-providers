# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Side-effect-free object actions for SmartCMP alarm alerts."""

from __future__ import annotations

from typing import Any, Mapping

from _object_actions_common import build_object_prompt_action
from smartcmp_provider.domain.alarms import available_alert_operations


_OPERATION_LABELS = {
    "mute": ("Mute", "静音", "warning"),
    "resolve": ("Resolve", "解决", "success"),
    "reopen": ("Reopen", "重新打开", "warning"),
}


def _prompt_action(alert_id: str, operation: str) -> dict[str, object] | None:
    """Build one validated alarm operation prompt."""
    label_en, label_zh, tone = _OPERATION_LABELS[operation]
    return build_object_prompt_action(
        operation,
        label_en=label_en,
        label_zh=label_zh,
        prompt_en=f"{label_en} alert {alert_id}",
        prompt_zh=f"{label_zh}告警 {alert_id}",
        confirmation_en=f"Confirm {label_en.lower()} alert {alert_id}?",
        confirmation_zh=f"确认{label_zh}告警 {alert_id}？",
        effect="mutate",
        tone=tone,
        requires_confirmation=True,
    )


def build_alert_object_actions(
    alert: Mapping[str, Any],
    *,
    operations: tuple[str, ...] | None = None,
    analyze_action_id: str = "analyze",
    include_analysis_action: bool = True,
) -> list[dict[str, object]]:
    """Build analysis plus status-valid operations for one alert."""
    alert_id = str(alert.get("id") or "").strip()
    if not alert_id:
        return []
    analyze = (
        build_object_prompt_action(
            analyze_action_id,
            label_en=(
                "View details" if analyze_action_id == "view_detail" else "Analyze"
            ),
            label_zh="查看详情" if analyze_action_id == "view_detail" else "分析",
            prompt_en=f"Analyze alert {alert_id}",
            prompt_zh=f"分析告警 {alert_id}",
        )
        if include_analysis_action
        else None
    )
    actions = [analyze] if analyze else []
    allowed = operations
    if allowed is None:
        allowed = tuple(
            operation.operation_id
            for operation in available_alert_operations(alert)
            if operation.capability_id == "smartcmp.alarms.operate"
        )
    for operation in allowed:
        if operation not in _OPERATION_LABELS:
            continue
        action = _prompt_action(alert_id, operation)
        if action:
            actions.append(action)
    return actions


def attach_alert_object_metadata(
    projection: dict[str, Any],
    *,
    alert: Mapping[str, Any],
    operations: tuple[str, ...] | None = None,
    analyze_action_id: str = "analyze",
    include_analysis_action: bool = True,
) -> dict[str, Any]:
    """Attach AtlasClaw object rendering to one Provider alert projection."""

    enriched = dict(projection)
    alert_id = str(alert.get("id") or projection.get("alert_id") or "").strip()
    alert_name = str(
        alert.get("name")
        or alert.get("policyName")
        or projection.get("name")
        or alert_id
    ).strip()
    action_source = dict(alert)
    action_source["id"] = alert_id
    enriched.update(
        {
            "object_type": "alarm_alert",
            "object_id": alert_id,
            "object_name": alert_name,
            "object_actions": build_alert_object_actions(
                action_source,
                operations=operations,
                analyze_action_id=analyze_action_id,
                include_analysis_action=include_analysis_action,
            ),
        }
    )
    return enriched
