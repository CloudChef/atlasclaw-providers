# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Dynamic object actions owned by the SmartCMP approval Domain Skill."""

from __future__ import annotations

import re
from urllib.parse import quote, urlencode

from _object_actions_common import (
    build_object_open_action,
    build_object_prompt_action,
    build_ui_hash_href,
    normalize_ui_base_url,
)


_APPROVAL_DETAIL_FROM_PARAMS = {"from": "normal", "fromPagePartUrl": "SR_MY_APPROVAL"}
_APPROVAL_APPLICATION_TYPES = {
    "PROVISION_BP",
    "TEAR_DOWN_APP",
    "PROCESS_NEW_PROJECT",
    "PROCESS_NEW_RESOURCEPOOL",
    "PROCESS_EXPAND_VM",
    "PROCESS_EXPAND_PROJECT",
    "DAY2_OPERATION",
    "PROCESS_EXPAND_RESOURCEPOOL",
    "VM_OPERATION",
    "TASK_EXECUTION_REQUEST",
}
_REQUEST_ID_PATTERN = re.compile(r"^[A-Z]{3}\d{14}$", re.IGNORECASE)
_REQUEST_ID_FIELD_NAMES = (
    "requestId",
    "request_id",
    "workflowId",
    "workflow_id",
    "requestNo",
    "requestNumber",
    "customizedId",
)


def build_approval_object_actions(
    base_url: str,
    item: dict,
    *,
    include_detail_actions: bool = False,
) -> list[dict[str, object]]:
    """Build the actions currently available for one approval object.

    Args:
        base_url: SmartCMP API or browser root.
        item: Approval row or detail carrying a user-facing request ID.
        include_detail_actions: Whether the object contains enough detail for
            analysis and decision intents.

    Returns:
        Provider-agnostic actions for the current approval projection.
    """
    request_id = _approval_request_id(item)
    actions: list[dict[str, object]] = []
    open_action = build_object_open_action(build_approval_page_href(base_url, item))
    if open_action:
        actions.append(open_action)

    # Action availability follows the producing Tool projection, not merely the
    # object type: list rows expose detail lookup, while verified details expose
    # analysis and decision intents.
    if request_id and not include_detail_actions:
        detail_action = build_object_prompt_action(
            "view_detail",
            label_en="View details",
            label_zh="查看详情",
            prompt_en=f"Show approval details for {request_id}",
            prompt_zh=f"查看 {request_id} 的审批详情",
        )
        if detail_action:
            actions.insert(0, detail_action)
        return actions

    if not request_id:
        return actions

    analyze_action = build_object_prompt_action(
        "analyze",
        label_en="Analyze",
        label_zh="分析",
        prompt_en=f"Run read-only approval analysis for {request_id}",
        prompt_zh=f"只读分析审批请求 {request_id}",
    )
    # Mutation actions are Agent intents, not direct SmartCMP writes. Core still
    # applies its confirmation gate before the owning Skill may execute a Tool.
    approve_action = build_object_prompt_action(
        "approve",
        label_en="Approve",
        label_zh="同意",
        prompt_en=f"Approve {request_id}; the user confirmed this approval in the UI.",
        prompt_zh=f"批准 {request_id}，用户已在界面确认执行。",
        effect="mutate",
        tone="success",
        requires_confirmation=True,
        confirmation_en=f"Confirm approving {request_id}?",
        confirmation_zh=f"确认同意 {request_id}？",
    )
    reject_action = build_object_prompt_action(
        "reject",
        label_en="Reject",
        label_zh="拒绝",
        prompt_en=(
            f"Reject {request_id}, reason: {{{{reason}}}}; "
            "the user confirmed this rejection in the UI."
        ),
        prompt_zh=f"拒绝 {request_id}，原因：{{{{reason}}}}，用户已在界面确认执行。",
        effect="mutate",
        tone="danger",
        requires_confirmation=True,
        confirmation_en=f"Provide a rejection reason for {request_id}.",
        confirmation_zh=f"请填写拒绝 {request_id} 的原因。",
        prompt_template=True,
        inputs=[
            {
                "name": "reason",
                "display_label": {
                    "default": "Rejection reason",
                    "translations": {
                        "en-US": "Rejection reason",
                        "zh-CN": "拒绝原因",
                    },
                },
                "type": "textarea",
                "required": True,
            }
        ],
    )
    actions.extend(
        action
        for action in (analyze_action, approve_action, reject_action)
        if action is not None
    )
    return actions


def build_approval_page_href(base_url: str, item: dict) -> str:
    """Build the verified SmartCMP detail URL for one approval object."""
    hash_route = _build_approval_hash_route(item)
    if not hash_route:
        return ""
    return build_ui_hash_href(normalize_ui_base_url(base_url), hash_route)


def _approval_request_id(item: dict) -> str:
    if not isinstance(item, dict):
        return ""
    request_id = _request_id_from_mapping(item)
    if request_id:
        return request_id

    current_activity = item.get("currentActivity")
    request_id = _request_id_from_mapping(current_activity)
    if request_id:
        return request_id
    if not isinstance(current_activity, dict):
        return ""

    approval_requests = current_activity.get("approvalRequests")
    if not isinstance(approval_requests, list):
        return ""
    for approval_request in approval_requests:
        request_id = _request_id_from_mapping(approval_request)
        if request_id:
            return request_id
    return ""


def _request_id_from_mapping(mapping: object) -> str:
    if not isinstance(mapping, dict):
        return ""
    for field_name in _REQUEST_ID_FIELD_NAMES:
        candidate = _text(mapping.get(field_name))
        if _REQUEST_ID_PATTERN.fullmatch(candidate):
            return candidate
    return ""


def _build_approval_hash_route(item: dict) -> str:
    if not isinstance(item, dict):
        return ""

    exts = item.get("exts") if isinstance(item.get("exts"), dict) else {}
    approval_type = _text(exts.get("approval_type") or item.get("approval_type"))
    approval_id = _text(exts.get("approval_id") or item.get("approval_id"))
    approval_state = _text(
        exts.get("approval_state") or item.get("approval_state")
    ).upper()
    row_id = _text(item.get("id"))

    if approval_type == "REQUEST_INVENTORY" and row_id:
        return (
            f"#/main/service-request/my-approval/edit/{quote(row_id, safe='')}"
            f"?{urlencode({'fromPagePartUrl': 'SR_MY_APPROVAL'})}"
        )
    if not approval_state or not approval_id:
        return ""

    stage = "pendingApproval" if approval_state == "PENDING" else "doneApproval"
    route_type = approval_type if approval_type in _APPROVAL_APPLICATION_TYPES else "GENERIC"
    return (
        f"#/main/new-application/{quote(stage, safe='')}/"
        f"{quote(route_type, safe='')}/{quote(approval_id, safe='')}"
        f"?{urlencode(_APPROVAL_DETAIL_FROM_PARAMS)}"
    )


def _text(value: object) -> str:
    return str(value).strip() if value not in (None, "") else ""
