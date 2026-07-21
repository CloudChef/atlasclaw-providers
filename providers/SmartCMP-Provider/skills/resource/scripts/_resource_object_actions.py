# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Dynamic object actions owned by the SmartCMP resource Domain Skill."""

from __future__ import annotations

from _object_actions_common import (
    build_object_open_action,
    build_object_prompt_action,
    build_resource_page_href,
)


def build_resource_object_actions(
    base_url: str,
    resource_id: str,
    category: str = "virtual-machines",
    *,
    resource_name: str = "",
    include_detail_action: bool = False,
    include_analysis_action: bool = False,
    include_operations_action: bool = False,
) -> list[dict[str, object]]:
    """Build the actions available for the current resource projection.

    Args:
        base_url: SmartCMP API or browser root.
        resource_id: SmartCMP resource UUID or external route identifier.
        category: Verified SmartCMP UI resource category.
        resource_name: Human-visible resource name used in Agent prompts.
        include_detail_action: Whether this projection exposes detail lookup.
        include_analysis_action: Whether this projection exposes analysis.
        include_operations_action: Whether this projection exposes operation discovery.

    Returns:
        Provider-agnostic actions for the current resource projection.
    """
    # The producing Tool selects these flags from the data it actually resolved;
    # object type alone must not invent detail, analysis, or operation actions.
    target = str(resource_id or resource_name or "").strip()
    actions: list[dict[str, object]] = []
    if target and include_detail_action:
        detail_action = build_object_prompt_action(
            "view_detail",
            label_en="View details",
            label_zh="查看详情",
            prompt_en=f"Show resource details for {target}",
            prompt_zh=f"查看 {target} 的资源详情",
        )
        if detail_action:
            actions.append(detail_action)

    open_action = build_object_open_action(
        build_resource_page_href(base_url, resource_id, category=category)
    )
    if open_action:
        actions.append(open_action)

    if target and include_analysis_action:
        analyze_action = build_object_prompt_action(
            "analyze",
            label_en="Analyze",
            label_zh="分析",
            prompt_en=f"Analyze resource {target}",
            prompt_zh=f"分析资源 {target}",
        )
        if analyze_action:
            actions.append(analyze_action)
    if target and include_operations_action:
        operations_action = build_object_prompt_action(
            "list_operations",
            label_en="Operations",
            label_zh="操作",
            prompt_en=f"List available operations for resource {target}",
            prompt_zh=f"查看资源 {target} 的可用操作",
        )
        if operations_action:
            actions.append(operations_action)
    return actions
