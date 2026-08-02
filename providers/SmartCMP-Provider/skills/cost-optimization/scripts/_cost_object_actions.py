# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Side-effect-free object actions for SmartCMP cost recommendations."""

from __future__ import annotations

from typing import Any, Mapping

from _object_actions_common import build_object_prompt_action
from smartcmp_provider.domain.cost import available_cost_operations


def build_cost_object_actions(
    item: Mapping[str, Any],
    *,
    analyze_action_id: str = "analyze",
    include_analysis_action: bool = True,
) -> list[dict[str, object]]:
    """Build actions allowed by the recommendation's remediation state."""
    violation_id = str(item.get("id") or item.get("violationId") or "").strip()
    if not violation_id:
        return []
    analyze = (
        build_object_prompt_action(
            analyze_action_id,
            label_en=(
                "View details" if analyze_action_id == "view_detail" else "Analyze"
            ),
            label_zh="查看详情" if analyze_action_id == "view_detail" else "分析",
            prompt_en=f"Analyze cost optimization recommendation {violation_id}",
            prompt_zh=f"分析成本优化建议 {violation_id}",
        )
        if include_analysis_action
        else None
    )
    actions = [analyze] if analyze else []
    available = {
        operation.operation_id for operation in available_cost_operations(item)
    }
    if "track" in available:
        track = build_object_prompt_action(
            "track",
            label_en="Track remediation",
            label_zh="跟踪修复",
            prompt_en=f"Track cost optimization remediation {violation_id}",
            prompt_zh=f"跟踪成本优化修复 {violation_id}",
        )
        if track:
            actions.append(track)
    elif "remediate" in available:
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


def attach_cost_object_metadata(
    projection: dict[str, Any],
    *,
    recommendation: Mapping[str, Any],
    analyze_action_id: str = "analyze",
    include_analysis_action: bool = True,
) -> dict[str, Any]:
    """Attach AtlasClaw object rendering to one Provider cost projection.

    Args:
        projection: Safe recommendation result returned to AtlasClaw.
        recommendation: SmartCMP recommendation facts used for action state.
        analyze_action_id: AtlasClaw presentation ID for the read action.

    Returns:
        A copy containing object identity and AtlasClaw object actions.
    """

    enriched = dict(projection)
    violation_id = str(
        recommendation.get("id")
        or recommendation.get("violationId")
        or projection.get("violationId")
        or ""
    ).strip()
    action_source = dict(recommendation)
    action_source["violationId"] = violation_id
    enriched.update(
        {
            "object_type": "cost_optimization_recommendation",
            "object_id": violation_id,
            "object_name": str(
                recommendation.get("policyName")
                or recommendation.get("resourceName")
                or violation_id
            ).strip(),
            "object_actions": build_cost_object_actions(
                action_source,
                analyze_action_id=analyze_action_id,
                include_analysis_action=include_analysis_action,
            ),
        }
    )
    return enriched
