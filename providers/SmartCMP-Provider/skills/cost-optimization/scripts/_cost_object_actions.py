# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Side-effect-free object actions for SmartCMP cost recommendations."""

from __future__ import annotations

from typing import Any, Mapping

from _object_actions_common import build_object_prompt_action


_COMPLETED_STATUSES = {"FIXED", "RESOLVED", "SUCCESS", "DONE", "CLOSED"}


def build_cost_object_actions(
    item: Mapping[str, Any], *, analyze_action_id: str = "analyze"
) -> list[dict[str, object]]:
    """Build actions allowed by the recommendation's remediation state."""
    violation_id = str(item.get("id") or item.get("violationId") or "").strip()
    if not violation_id:
        return []
    analyze = build_object_prompt_action(
        analyze_action_id,
        label_en="View details" if analyze_action_id == "view_detail" else "Analyze",
        label_zh="查看详情" if analyze_action_id == "view_detail" else "分析",
        prompt_en=f"Analyze cost optimization recommendation {violation_id}",
        prompt_zh=f"分析成本优化建议 {violation_id}",
    )
    actions = [analyze] if analyze else []
    status = str(item.get("status") or "").strip().upper()
    has_execution = bool(item.get("taskInstanceId"))
    executable = bool(item.get("fixType") or item.get("taskDefinitionName") or item.get("taskDefinition"))
    if has_execution:
        track = build_object_prompt_action(
            "track",
            label_en="Track remediation",
            label_zh="跟踪修复",
            prompt_en=f"Track cost optimization remediation {violation_id}",
            prompt_zh=f"跟踪成本优化修复 {violation_id}",
        )
        if track:
            actions.append(track)
    elif executable and status not in _COMPLETED_STATUSES:
        remediate = build_object_prompt_action(
            "remediate",
            label_en="Remediate",
            label_zh="修复",
            prompt_en=f"Remediate cost optimization recommendation {violation_id}",
            prompt_zh=f"修复成本优化建议 {violation_id}",
            confirmation_en=f"Confirm remediating cost optimization recommendation {violation_id}?",
            confirmation_zh=f"确认修复成本优化建议 {violation_id}？",
            effect="mutate",
            tone="warning",
            requires_confirmation=True,
        )
        if remediate:
            actions.append(remediate)
    return actions
