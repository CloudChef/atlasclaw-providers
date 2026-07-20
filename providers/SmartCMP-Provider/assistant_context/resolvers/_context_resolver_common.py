# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Fail-closed request-user configuration and helpers for embedded page context."""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from typing import Any, Callable
from urllib.parse import quote, urlparse, urlunparse

import requests

try:
    from _presentation import (
        build_open_action,
        build_prompt_action,
        localized_text,
    )
    from _request_user_transport import (
        RequestUserConfigError,
        load_request_user_transport,
        suppress_insecure_request_warning,
    )
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _presentation import (
        build_open_action,
        build_prompt_action,
        localized_text,
    )
    from _request_user_transport import (
        RequestUserConfigError,
        load_request_user_transport,
        suppress_insecure_request_warning,
    )


class ContextConfigError(RuntimeError):
    """Raised before Provider I/O when request-user context configuration is invalid."""


RequestGet = Callable[..., Any]
CATALOG_ENTITY_CLASS = "io.cloudchef.yacmp.core.catalog.Catalog"
RESOURCE_ENTITY_CLASS = "io.cloudchef.yacmp.core.resource.Resource"
_CATALOG_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
_REQUEST_ID = re.compile(r"^[A-Z]{3}\d{14}$")


def load_context_config() -> tuple[str, dict[str, str], int]:
    """Load only an explicit instance and request-scoped Host authentication cookie.

    Provider/user tokens, configured cookies, and credentials are intentionally ignored.
    This resolver path never imports the general SmartCMP helper, so it cannot auto-login.
    """
    try:
        return load_request_user_transport()
    except RequestUserConfigError as exc:
        raise ContextConfigError(str(exc)) from exc


BASE_URL, HEADERS, REQUEST_TIMEOUT = load_context_config()


def exact_uuid(value: Any) -> str:
    """Return a canonical UUID or an empty string when the external ID is invalid."""
    normalized = str(value or "").strip().lower()
    try:
        parsed = uuid.UUID(normalized)
    except (ValueError, AttributeError):
        return ""
    return normalized if str(parsed) == normalized else ""


def exact_catalog_id(value: str) -> str:
    """Validate UUID and built-in SmartCMP catalog identifiers without URL parts."""
    normalized = str(value or "").strip()
    return normalized if _CATALOG_ID.fullmatch(normalized) else ""


def exact_request_id(value: Any) -> str:
    """Return one user-visible SmartCMP workflow ID or an empty string."""
    normalized = str(value or "").strip().upper()
    return normalized if _REQUEST_ID.fullmatch(normalized) else ""


def text(value: Any) -> str:
    """Return a trimmed scalar string while excluding nested provider data."""
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


def _ui_hash_href(route: str, *, query: str = "") -> str:
    parsed = urlparse(BASE_URL)
    ui_path = parsed.path.removesuffix("/platform-api").rstrip("/")
    ui_base_url = urlunparse((parsed.scheme, parsed.netloc, ui_path, "", "", ""))
    href = f"{ui_base_url}/#/{route.lstrip('/')}"
    return f"{href}?{query}" if query else href


def _open_action(href: str) -> dict[str, object]:
    action = build_open_action(href)
    assert action is not None
    return action


def _prompt_action(
    action_id: str,
    *,
    label_en: str,
    label_zh: str,
    prompt_en: str,
    prompt_zh: str,
    effect: str = "read",
    tone: str = "default",
) -> dict[str, object]:
    action = build_prompt_action(
        action_id,
        label_en=label_en,
        label_zh=label_zh,
        prompt_en=prompt_en,
        prompt_zh=prompt_zh,
        effect=effect,
        tone=tone,
    )
    assert action is not None
    return action


def build_approval_context_actions(
    approval_type: str,
    approval_id: str,
) -> list[dict[str, object]]:
    """Build navigation and ordinary Chat intents for one validated pending approval."""
    route = "/".join(
        (
            "main/new-application/pendingApproval",
            quote(approval_type, safe=""),
            quote(approval_id, safe=""),
        )
    )
    return [
        _open_action(_ui_hash_href(route, query="from=normal&fromPagePartUrl=SR_MY_APPROVAL")),
        _prompt_action(
            "analyze",
            label_en="Analyze",
            label_zh="分析",
            prompt_en="Run read-only analysis for the approval request on the current page",
            prompt_zh="只读分析当前页面的审批请求",
        ),
        _approval_approve_action(),
        _approval_reject_action(),
    ]


def _approval_approve_action() -> dict[str, object]:
    """Build the ordinary Chat intent for approving the current page object."""
    action = build_prompt_action(
        "approve",
        label_en="Approve",
        label_zh="同意",
        prompt_en=(
            "The user confirmed in the UI: approve the approval request on the current page"
        ),
        prompt_zh="用户已在界面中确认：批准当前页面的审批请求",
        effect="mutate",
        tone="success",
        requires_confirmation=True,
        confirmation_message_en="Confirm approval of the request on the current page?",
        confirmation_message_zh="确认批准当前页面的审批请求吗？",
    )
    assert action is not None
    return action


def _approval_reject_action() -> dict[str, object]:
    """Build the ordinary Chat intent for rejecting the current page object."""
    action = build_prompt_action(
        "reject",
        label_en="Reject",
        label_zh="拒绝",
        prompt_en=(
            "The user confirmed in the UI: reject the approval request on the current page, "
            "reason: {{reason}}"
        ),
        prompt_zh="用户已在界面中确认：拒绝当前页面的审批请求，原因：{{reason}}",
        effect="mutate",
        tone="danger",
        prompt_template=True,
        requires_confirmation=True,
        confirmation_message_en="Confirm rejection of the request on the current page?",
        confirmation_message_zh="确认拒绝当前页面的审批请求吗？",
        inputs=[
            {
                "name": "reason",
                "display_label": localized_text("Rejection reason", zh_cn="拒绝原因"),
                "type": "textarea",
                "required": True,
            }
        ],
    )
    assert action is not None
    return action


def build_catalog_context_actions(catalog_id: str) -> list[dict[str, object]]:
    """Build navigation and a normal Chat request intent for one validated catalog."""
    route = f"main/catalog-ui/request/{quote(catalog_id, safe='')}"
    return [
        _open_action(_ui_hash_href(route)),
        _prompt_action(
            "request",
            label_en="Request",
            label_zh="申请",
            prompt_en="Request the catalog item on the current page",
            prompt_zh="申请当前页面的目录项",
            effect="mutate",
        ),
    ]


def build_request_context_actions(
    application_type: str,
    request_id: str,
) -> list[dict[str, object]]:
    """Build navigation and exact status lookup for one validated request."""
    route = "/".join(
        (
            "main/new-process/myApplication",
            quote(application_type, safe=""),
            quote(request_id, safe=""),
        )
    )
    return [
        _open_action(_ui_hash_href(route)),
        _prompt_action(
            "status",
            label_en="Status",
            label_zh="状态",
            prompt_en="Check the status of the request on the current page",
            prompt_zh="查看当前页面申请的状态",
        ),
    ]


def build_resource_context_actions(
    resource_id: str,
    expected_kind: str,
) -> list[dict[str, object]]:
    """Build navigation and dynamic operation-discovery intents for one validated resource."""
    encoded_id = quote(resource_id, safe="")
    route = (
        f"main/virtual-machines/{encoded_id}/details"
        if expected_kind == "virtual_machine"
        else f"main/cloud-resource/{encoded_id}"
    )
    return [
        _open_action(_ui_hash_href(route)),
        _prompt_action(
            "list_operations",
            label_en="Operations",
            label_zh="操作",
            prompt_en="List available operations for the resource on the current page",
            prompt_zh="查看当前页面资源的可用操作",
        ),
    ]


def get_json(
    path: str,
    *,
    request_get: RequestGet = requests.get,
    params: dict[str, Any] | None = None,
) -> Any:
    """Execute one request-user authenticated, non-mutating Provider GET."""
    # Resolver stdout must remain a single JSON value. urllib3 writes this one
    # expected warning to stderr for verify=False, and the Markdown Tool runtime
    # preserves stderr as Tool output. Keep the suppression local and category-
    # specific so Provider diagnostics, unrelated warnings, and exceptions remain
    # observable and continue to fail closed.
    with suppress_insecure_request_warning():
        response = request_get(
            f"{BASE_URL}/{path.lstrip('/')}",
            headers=HEADERS,
            params=params,
            verify=False,
            timeout=REQUEST_TIMEOUT,
        )
    response.raise_for_status()
    return response.json()


def has_instance_permission(
    entity_class: str,
    entity_id: str,
    permission: str,
    *,
    request_get: RequestGet = requests.get,
) -> bool:
    """Check one effective current-user instance ACL from the read-only permission query."""
    try:
        payload = get_json(
            "acl/queryCurrentUserPermissions",
            request_get=request_get,
            params={
                "entityClassNames": entity_class,
                "entityInstanceIds": entity_id,
            },
        )
    except (requests.exceptions.RequestException, TypeError, ValueError):
        return False
    if not isinstance(payload, list):
        return False

    exact_entries: list[dict[str, Any]] = []
    class_entries: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        entity = item.get("entityClass")
        if not isinstance(entity, dict) or text(entity.get("className")) != entity_class:
            continue
        instance_id = text(entity.get("instanceId"))
        if instance_id == entity_id:
            exact_entries.append(item)
        elif instance_id in {"", "-1"}:
            class_entries.append(item)

    for item in exact_entries + class_entries:
        permissions = item.get("permissions")
        if not isinstance(permissions, list):
            continue
        permission_ids = {
            text(value.get("id")) if isinstance(value, dict) else text(value)
            for value in permissions
        }
        if permission in permission_ids:
            return True
    return False


def success_object(
    *,
    object_type: str,
    object_id: str,
    name: str,
    state: str,
    attributes: dict[str, Any],
    object_actions: list[dict[str, object]],
) -> dict[str, Any]:
    """Build the strict provider-neutral object and display-only action envelope."""
    return {
        "success": True,
        "object": {
            "type": object_type,
            "id": object_id,
            "name": name,
            "state": state,
            "attributes": {key: value for key, value in attributes.items() if value != ""},
        },
        "object_actions": object_actions,
    }


def write_result(result: dict[str, Any]) -> None:
    """Write one coordination JSON value without credentials or raw Provider payloads."""
    print(json.dumps(result, ensure_ascii=False))
