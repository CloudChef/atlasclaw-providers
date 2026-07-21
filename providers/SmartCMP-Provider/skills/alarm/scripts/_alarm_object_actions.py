# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Side-effect-free object actions for SmartCMP alarm alerts."""

from __future__ import annotations

from typing import Any, Mapping

from _object_actions_common import build_object_prompt_action


_STATUS_OPERATIONS = {
    "ALERT_FIRING": ("mute", "resolve"),
    "ALERT_MUTED": ("resolve", "reopen"),
    "ALERT_RESOLVED": ("reopen",),
}
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
) -> list[dict[str, object]]:
    """Build analysis plus status-valid operations for one alert."""
    alert_id = str(alert.get("id") or "").strip()
    if not alert_id:
        return []
    analyze = build_object_prompt_action(
        analyze_action_id,
        label_en="View details" if analyze_action_id == "view_detail" else "Analyze",
        label_zh="查看详情" if analyze_action_id == "view_detail" else "分析",
        prompt_en=f"Analyze alert {alert_id}",
        prompt_zh=f"分析告警 {alert_id}",
    )
    actions = [analyze] if analyze else []
    allowed = operations
    if allowed is None:
        status = str(alert.get("status") or "").strip().upper()
        allowed = _STATUS_OPERATIONS.get(status, ())
    for operation in allowed:
        if operation not in _OPERATION_LABELS:
            continue
        action = _prompt_action(alert_id, operation)
        if action:
            actions.append(action)
    return actions
