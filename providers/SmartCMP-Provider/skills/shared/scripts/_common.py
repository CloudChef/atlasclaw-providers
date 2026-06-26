# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""SmartCMP Provider Common Utilities - Updated for SkillDeps Integration.

This module reads configuration from ATLASCLAW_PROVIDER_CONFIG and ATLASCLAW_COOKIES.
Webhook robot execution must pass an explicit ATLASCLAW_PROVIDER_INSTANCE and fails
closed if that instance is not configured.

Features:
  - Read configuration from SkillDeps (via environment variables)
  - Automatic URL normalization (adds /platform-api if missing)
  - Smart auth URL inference based on environment (SaaS vs Private)
  - Common HTTP headers generation
  - SSL warning suppression
  - Auto-login with username/password when cookie not provided

Usage:
  from _common import get_cmp_config, create_headers, require_config

Environment Variables (from SkillDeps):
  ATLASCLAW_COOKIES          - JSON string of all cookies from HTTP request
  ATLASCLAW_PROVIDER_CONFIG  - JSON string of provider configuration from atlasclaw.json
  ATLASCLAW_USER_ID          - Current user ID

Direct Environment Variables (local scripts):
  CMP_URL            - Base URL (IP, hostname, or full path)
  CMP_PROVIDER_TOKEN - Shared provider token for token-based authentication
  CMP_API_TOKEN      - Legacy API token for token-based authentication
  CMP_COOKIE         - Full session cookie string
  CMP_USERNAME       - Username for auto-login
  CMP_PASSWORD       - Password for auto-login
"""
import os
import sys
import json
import re
import urllib3
import requests
from urllib.parse import quote, urlencode, urlparse, urlunparse

# Suppress SSL warnings globally when this module is imported
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# API path that should be appended if missing
_API_PATH = "/platform-api"
_config_source_key = "_atlasclaw_config_source"
_config_source_skilldeps = "skilldeps"
_config_source_env = "env"
default_request_timeout = 60
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

# SaaS environment detection
# Domain suffix alone is not reliable because private deployments can also use
# smartcmp.cloud subdomains.
_SAAS_HOSTS = {
    "console.smartcmp.cloud",
    "account.smartcmp.cloud",
    "console.cloudchef.io",
}
_SAAS_AUTH_URL = "https://account.smartcmp.cloud/bss-api/api/authentication"


class ProviderConfigError(RuntimeError):
    """Raised when SkillDeps provider configuration is explicitly unusable."""


def normalize_url(url: str) -> str:
    """Normalize CMP URL to ensure it includes the /platform-api path."""
    if not url:
        return ""

    url = url.strip()

    # Add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    # Parse the URL
    parsed = urlparse(url)

    # Get the path and normalize it
    path = parsed.path.rstrip("/")

    # Check if path already ends with /platform-api
    if not path.endswith(_API_PATH):
        path = path + _API_PATH

    # Reconstruct the URL
    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        "",  # params
        "",  # query
        ""   # fragment
    ))

    return normalized


def normalize_ui_base_url(url: str) -> str:
    """Normalize a SmartCMP browser URL root for building user-facing links.

    Args:
        url: SmartCMP UI root or API root. Missing schemes default to HTTPS.

    Returns:
        Absolute UI base URL without a trailing slash or trailing ``/platform-api`` segment.
    """
    if not url:
        return ""

    normalized = url.strip()
    if not normalized:
        return ""
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"

    parsed = urlparse(normalized)
    path = parsed.path.rstrip("/")
    if path.endswith(_API_PATH):
        path = path[: -len(_API_PATH)].rstrip("/")

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        "",
        "",
        "",
    ))


def build_ui_hash_href(ui_base_url: str, hash_route: str) -> str:
    """Build an absolute SmartCMP hash-route URL.

    Args:
        ui_base_url: Browser-facing SmartCMP root.
        hash_route: Route such as ``#/main/virtual-machines/<id>/details``.

    Returns:
        Absolute browser URL, or an empty string when the UI root is unavailable.
    """
    normalized_base_url = normalize_ui_base_url(ui_base_url)
    if not normalized_base_url:
        return ""

    route = (hash_route or "").strip()
    if not route:
        return normalized_base_url
    if route.startswith("/#/"):
        return f"{normalized_base_url}{route}"
    if route.startswith("#/"):
        return f"{normalized_base_url}/{route}"
    if route.startswith("/"):
        return f"{normalized_base_url}/#{route}"
    return f"{normalized_base_url}/#/{route}"


def build_resource_page_href(
    base_url: str,
    resource_id: str,
    category: str = "virtual-machines",
) -> str:
    """Build a SmartCMP resource detail page URL for object actions.

    Args:
        base_url: SmartCMP instance base URL.
        resource_id: SmartCMP resource UUID or external route identifier.
        category: SmartCMP UI resource category path segment.

    Returns:
        Absolute browser URL for the resource detail page.
    """
    ui_base_url = normalize_ui_base_url(base_url)
    encoded_resource_id = quote(str(resource_id or ""), safe="")
    if not encoded_resource_id:
        return ""
    normalized_category = str(category or "virtual-machines").strip("/")
    return build_ui_hash_href(
        ui_base_url,
        f"#/main/{normalized_category}/{encoded_resource_id}/details",
    )


def infer_resource_page_category(resource: dict | None) -> str:
    """Infer the SmartCMP UI resource category only when the resource type is explicit.

    Args:
        resource: Resource-like metadata containing SmartCMP ``resourceType`` and/or
            ``componentType`` fields.

    Returns:
        The UI route category for known resource shapes, or an empty string when a
        safe object page cannot be inferred.
    """
    if not isinstance(resource, dict):
        return ""

    resource_type = str(resource.get("resourceType") or "").strip().lower()
    component_type = str(resource.get("componentType") or "").strip().lower()
    if resource_type in {"virtualmachine", "virtual_machine", "vm"}:
        return "virtual-machines"
    if "virtual_machine" in component_type:
        return "virtual-machines"
    if "machine.instance" in component_type or "windows_instance" in component_type:
        return "virtual-machines"
    return ""


def _localized_text(default: str, *, zh_cn: str, en_us: str | None = None) -> dict[str, object]:
    """Return the locale envelope consumed by AtlasClaw's generic action renderer."""
    default_text = str(default or "").strip()
    zh_text = str(zh_cn or "").strip()
    en_text = str(en_us if en_us is not None else default_text).strip()
    return {
        "default": default_text,
        "translations": {
            "en-US": en_text,
            "zh-CN": zh_text,
        },
    }


def _display_label(en_us: str, zh_cn: str) -> dict[str, object]:
    return _localized_text(en_us, zh_cn=zh_cn, en_us=en_us)


def _agent_prompt(en_us: str, zh_cn: str) -> dict[str, object]:
    return _localized_text(en_us, zh_cn=zh_cn, en_us=en_us)


def _confirmation_message(en_us: str, zh_cn: str) -> dict[str, object]:
    return _localized_text(en_us, zh_cn=zh_cn, en_us=en_us)


def escape_markdown_cell(value: object) -> str:
    """Render one value safely inside a Markdown table cell."""
    rendered = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    rendered = " ".join(rendered.split())
    return rendered.replace("|", "\\|")


def render_markdown_table(summary: str, headers: list[str], rows: list[list[object]]) -> str:
    """Render a provider script list result as a standard Markdown table.

    Args:
        summary: One-line count or empty-state summary shown above the table.
        headers: Visible table header labels.
        rows: Table row values aligned with ``headers``.

    Returns:
        Markdown table text. When ``rows`` is empty, only the summary is returned.
    """
    lines = [summary]
    if not rows:
        return "\n".join(lines)
    lines.extend(
        [
            "",
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
    )
    for row in rows:
        lines.append("| " + " | ".join(escape_markdown_cell(value) for value in row) + " |")
    return "\n".join(lines)


def build_object_open_action(
    href: str,
    *,
    action_id: str = "open_detail",
    label_en: str = "Open",
    label_zh: str = "打开",
) -> dict[str, object] | None:
    """Build a generic browser navigation action for a verified object URL.

    Args:
        href: Absolute SmartCMP UI URL for the target object page.
        action_id: Provider-stable action identifier.
        label_en: English display label.
        label_zh: Simplified Chinese display label.

    Returns:
        An ``open_url`` action, or ``None`` when no object URL is available.
    """
    normalized_href = str(href or "").strip()
    if not normalized_href:
        return None

    # Open actions are rendered as direct browser links by core. Returning None
    # is intentional when SmartCMP does not provide a verified object route; a
    # fallback list URL would make the provider action look object-specific when
    # it is not.
    return {
        "action_id": str(action_id or "open_detail"),
        "kind": "open_url",
        "display_label": _display_label(label_en, label_zh),
        "href": normalized_href,
        "effect": "navigate",
        "tone": "default",
    }


def build_object_prompt_action(
    action_id: str,
    *,
    label_en: str,
    label_zh: str,
    prompt_en: str,
    prompt_zh: str,
    effect: str = "read",
    tone: str = "default",
    requires_confirmation: bool = False,
    confirmation_en: str = "",
    confirmation_zh: str = "",
    prompt_template: bool = False,
    inputs: list[dict[str, object]] | None = None,
) -> dict[str, object] | None:
    """Build a generic agent-prompt action for object sidecar controls.

    Args:
        action_id: Provider-stable action identifier.
        label_en: English display label.
        label_zh: Simplified Chinese display label.
        prompt_en: English prompt or prompt template sent back to the agent.
        prompt_zh: Simplified Chinese prompt or prompt template sent back to the agent.
        effect: Declarative side effect category, such as ``read`` or ``mutate``.
        tone: UI tone hint consumed by the generic renderer.
        requires_confirmation: Whether the UI must confirm before submitting the prompt.
        confirmation_en: English confirmation message for mutating actions.
        confirmation_zh: Simplified Chinese confirmation message for mutating actions.
        prompt_template: Whether to emit ``agent_prompt_template`` instead of ``agent_prompt``.
        inputs: Optional input definitions used to fill prompt templates.

    Returns:
        An ``agent_prompt`` action, or ``None`` when required fields are blank.
    """
    normalized_action_id = str(action_id or "").strip()
    if not normalized_action_id or not str(prompt_en or "").strip() or not str(prompt_zh or "").strip():
        return None

    # The provider describes the action; core owns rendering and submits the
    # prompt back through the same conversation path as normal user input.
    # Mutating operations use confirmation metadata rather than provider-specific
    # UI code.
    action: dict[str, object] = {
        "action_id": normalized_action_id,
        "kind": "agent_prompt",
        "display_label": _display_label(label_en, label_zh),
        "effect": str(effect or "read"),
        "tone": str(tone or "default"),
    }
    prompt_key = "agent_prompt_template" if prompt_template else "agent_prompt"
    action[prompt_key] = _agent_prompt(prompt_en, prompt_zh)
    if requires_confirmation:
        action["requires_confirmation"] = True
        if confirmation_en or confirmation_zh:
            action["confirmation_message"] = _confirmation_message(
                confirmation_en or prompt_en,
                confirmation_zh or prompt_zh,
            )
    if inputs:
        action["inputs"] = inputs
    return action


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
    """Build provider-agnostic actions for a SmartCMP resource object.

    Args:
        base_url: SmartCMP instance base URL.
        resource_id: SmartCMP resource UUID or external route identifier.
        category: SmartCMP UI resource category path segment.
        resource_name: Human-visible resource name used as object context.
        include_detail_action: Whether to expose a detail lookup prompt.
        include_analysis_action: Whether to expose a compliance analysis prompt.
        include_operations_action: Whether to expose the available-operation lookup prompt.

    Returns:
        A list suitable for the generic ``object_actions`` metadata contract.
    """
    target = str(resource_id or resource_name or "").strip()
    actions: list[dict[str, object]] = []
    if target and include_detail_action:
        action = build_object_prompt_action(
            "view_detail",
            label_en="View details",
            label_zh="查看详情",
            prompt_en=f"Show resource details for {target}",
            prompt_zh=f"查看 {target} 的资源详情",
        )
        if action:
            actions.append(action)

    # Browser navigation must be based on a known SmartCMP route category. When
    # a resource type cannot be mapped safely, build_resource_page_href returns
    # an empty href and no open action is emitted.
    page_href = build_resource_page_href(base_url, resource_id, category=category)
    action = build_object_open_action(page_href)
    if action:
        actions.append(action)

    if target and include_analysis_action:
        action = build_object_prompt_action(
            "analyze",
            label_en="Analyze",
            label_zh="分析",
            prompt_en=f"Analyze resource {target}",
            prompt_zh=f"分析资源 {target}",
        )
        if action:
            actions.append(action)
    if target and include_operations_action:
        action = build_object_prompt_action(
            "list_operations",
            label_en="Operations",
            label_zh="操作",
            prompt_en=f"List available operations for resource {target}",
            prompt_zh=f"查看资源 {target} 的可用操作",
        )
        if action:
            actions.append(action)
    return actions


def build_approval_page_href(base_url: str, item: dict) -> str:
    """Build the SmartCMP approval page URL used by approval actions.

    The route logic mirrors SmartCMP's My Approval list UI. It builds item detail
    links only from fields that the UI itself uses. When the API response does not
    include enough route fields, this returns an empty string instead of falling
    back to a list page, because ``open_url`` actions must target the object itself.

    Args:
        base_url: SmartCMP instance base URL.
        item: SmartCMP approval row from ``generic-request/current-activity-approval``.

    Returns:
        Absolute browser URL for the approval row, or an empty string.
    """
    ui_base_url = normalize_ui_base_url(base_url)
    hash_route = _build_approval_hash_route(item)
    return build_ui_hash_href(ui_base_url, hash_route) if hash_route else ""


def build_approval_object_actions(
    base_url: str,
    item: dict,
    *,
    include_detail_actions: bool = False,
) -> list[dict[str, object]]:
    """Build provider-agnostic actions for a SmartCMP approval object.

    Args:
        base_url: SmartCMP instance base URL.
        item: SmartCMP approval row from ``generic-request/current-activity-approval``.
        include_detail_actions: Whether to include detail-only analysis and decision actions.

    Returns:
        A list suitable for the generic ``object_actions`` metadata contract.
    """
    request_id = _approval_request_id(item)
    page_href = build_approval_page_href(base_url, item)
    actions: list[dict[str, object]] = []
    if page_href:
        actions.append(
            {
                "action_id": "open_detail",
                "kind": "open_url",
                "display_label": _display_label("Open", "打开"),
                "href": page_href,
                "effect": "navigate",
                "tone": "default",
            }
        )
    if request_id and not include_detail_actions:
        # List rows should expose a read-only transition into the detail view.
        # Decision actions are reserved for the detail response so the user sees
        # the request context before approving or rejecting.
        actions.insert(
            0,
            {
                "action_id": "view_detail",
                "kind": "agent_prompt",
                "display_label": _display_label("View details", "查看详情"),
                "agent_prompt": _agent_prompt(
                    f"Show approval details for {request_id}",
                    f"查看 {request_id} 的审批详情",
                ),
                "effect": "read",
                "tone": "default",
            },
        )
    if request_id and include_detail_actions:
        # Detail responses have enough context to expose mutating decisions.
        # They still execute through agent prompts so approval/rejection scripts
        # keep validating SmartCMP request IDs server-side.
        actions.extend(
            [
                {
                    "action_id": "analyze",
                    "kind": "agent_prompt",
                    "display_label": _display_label("Analyze", "分析"),
                    "agent_prompt": _agent_prompt(
                        f"Run read-only approval analysis for {request_id}",
                        f"只读分析审批请求 {request_id}",
                    ),
                    "effect": "read",
                    "tone": "default",
                },
                {
                    "action_id": "approve",
                    "kind": "agent_prompt",
                    "display_label": _display_label("Approve", "同意"),
                    "agent_prompt": _agent_prompt(
                        f"Approve {request_id}; the user confirmed this approval in the UI.",
                        f"批准 {request_id}，用户已在界面确认执行。",
                    ),
                    "confirmation_message": _confirmation_message(
                        f"Confirm approving {request_id}?",
                        f"确认同意 {request_id}？",
                    ),
                    "effect": "mutate",
                    "tone": "success",
                    "requires_confirmation": True,
                },
                {
                    "action_id": "reject",
                    "kind": "agent_prompt",
                    "display_label": _display_label("Reject", "拒绝"),
                    "agent_prompt_template": _agent_prompt(
                        (
                            f"Reject {request_id}, reason: {{{{reason}}}}; "
                            "the user confirmed this rejection in the UI."
                        ),
                        f"拒绝 {request_id}，原因：{{{{reason}}}}，用户已在界面确认执行。",
                    ),
                    "confirmation_message": _confirmation_message(
                        f"Provide a rejection reason for {request_id}.",
                        f"请填写拒绝 {request_id} 的原因。",
                    ),
                    "effect": "mutate",
                    "tone": "danger",
                    "requires_confirmation": True,
                    "inputs": [
                        {
                            "name": "reason",
                            "display_label": _display_label("Rejection reason", "拒绝原因"),
                            "type": "textarea",
                            "required": True,
                        }
                    ],
                },
            ]
        )
    return actions


def _approval_request_id(item: dict) -> str:
    """Return a canonical user-facing SmartCMP Request ID from known payload shapes."""
    if not isinstance(item, dict):
        return ""

    request_id = _request_id_from_mapping(item)
    if request_id:
        return request_id

    current_activity = item.get("currentActivity")
    request_id = _request_id_from_mapping(current_activity)
    if request_id:
        return request_id

    if isinstance(current_activity, dict):
        approval_requests = current_activity.get("approvalRequests")
        if isinstance(approval_requests, list):
            for approval_request in approval_requests:
                request_id = _request_id_from_mapping(approval_request)
                if request_id:
                    return request_id
    return ""


def _request_id_from_mapping(mapping: object) -> str:
    """Extract a validated SmartCMP Request ID from a mapping."""
    if not isinstance(mapping, dict):
        return ""
    for field_name in _REQUEST_ID_FIELD_NAMES:
        candidate = _text_value(mapping.get(field_name))
        if _REQUEST_ID_PATTERN.fullmatch(candidate):
            return candidate
    return ""


def _build_approval_hash_route(item: dict) -> str:
    """Return the SmartCMP hash route for a My Approval row."""
    if not isinstance(item, dict):
        return ""

    exts = item.get("exts") if isinstance(item.get("exts"), dict) else {}
    approval_type = _text_value(exts.get("approval_type") or item.get("approval_type"))
    approval_id = _text_value(exts.get("approval_id") or item.get("approval_id"))
    approval_state = _text_value(exts.get("approval_state") or item.get("approval_state")).upper()
    row_id = _text_value(item.get("id"))

    # SmartCMP uses a separate service-request editor route for inventory
    # approvals. Those rows are keyed by the row id, not by approval_id.
    if approval_type == "REQUEST_INVENTORY" and row_id:
        return (
            f"#/main/service-request/my-approval/edit/{quote(row_id, safe='')}"
            f"?{urlencode({'fromPagePartUrl': 'SR_MY_APPROVAL'})}"
        )

    # Application approvals reuse the new-application route and need the
    # approval state to choose pending vs. completed tabs. Unknown application
    # types intentionally collapse to GENERIC, matching SmartCMP's own route.
    if approval_state and approval_id:
        stage = "pendingApproval" if approval_state == "PENDING" else "doneApproval"
        route_type = approval_type if approval_type in _APPROVAL_APPLICATION_TYPES else "GENERIC"
        return (
            f"#/main/new-application/{quote(stage, safe='')}/"
            f"{quote(route_type, safe='')}/{quote(approval_id, safe='')}"
            f"?{urlencode(_APPROVAL_DETAIL_FROM_PARAMS)}"
        )

    return ""


def _text_value(value: object) -> str:
    """Normalize a route field from SmartCMP's loosely typed JSON payload."""
    if value in (None, ""):
        return ""
    return str(value).strip()


def _infer_auth_url(cmp_url: str) -> str:
    """Infer authentication URL from CMP base URL."""
    if not cmp_url:
        return ""

    url = cmp_url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    # Only canonical SmartCMP SaaS hosts on the default HTTPS port should route
    # to the shared SaaS authentication API.
    if hostname in _SAAS_HOSTS and parsed.port in (None, 443):
        return _SAAS_AUTH_URL

    # Private deployment
    return f"{parsed.scheme}://{parsed.netloc}/platform-api/login"


def _resolve_auth_url(cmp_url: str, explicit_auth_url: str = "") -> str:
    """Resolve the auth URL using explicit configuration first, then inference."""
    explicit_auth_url = (explicit_auth_url or "").strip()
    if explicit_auth_url:
        if not explicit_auth_url.startswith(("http://", "https://")):
            explicit_auth_url = f"https://{explicit_auth_url}"
        return explicit_auth_url
    return _infer_auth_url(cmp_url)


def _coerce_request_timeout(value: object) -> int:
    """Return a positive request timeout in seconds, falling back to the provider default."""
    try:
        timeout = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default_request_timeout
    return timeout if timeout > 0 else default_request_timeout


def get_request_timeout(instance: dict | None = None) -> int:
    """Resolve the SmartCMP HTTP timeout from provider config or local script environment.

    Args:
        instance: Provider instance configuration returned by ``require_config``.

    Returns:
        Positive timeout in seconds. Provider configuration takes precedence;
        ``CMP_TIMEOUT`` is for direct local script execution; the default is 60 seconds.
    """
    if isinstance(instance, dict):
        if instance.get("timeout") not in (None, ""):
            return _coerce_request_timeout(instance.get("timeout"))
        if instance.get(_config_source_key) == _config_source_skilldeps:
            return default_request_timeout
    return _coerce_request_timeout(os.environ.get("CMP_TIMEOUT", default_request_timeout))


def request_timeout(instance: dict | None = None) -> int:
    """Resolve the request timeout for scripts that use the imported provider config."""
    return get_request_timeout(INSTANCE if instance is None else instance)


def _auto_login(auth_url: str, username: str, password: str, timeout: int | None = None) -> str:
    """Auto-login to SmartCMP and get session cookie."""
    import hashlib

    # Auto-detect: if password is not 32-char hex (MD5 format), auto-encrypt it
    if not (len(password) == 32 and all(c in '0123456789abcdefABCDEF' for c in password)):
        password = hashlib.md5(password.encode()).hexdigest()

    try:
        resp = requests.post(
            auth_url,
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            verify=False,
            timeout=timeout or default_request_timeout,
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Login failed: HTTP {resp.status_code}")

        # Build cookie string from response cookies
        cookies = resp.cookies.get_dict()
        body = {}

        # Also try to get token from response body
        try:
            body = resp.json()
            if "token" in body:
                cookies["CloudChef-Authenticate"] = body["token"]
            if "refreshToken" in body:
                cookies["CloudChef-Authenticate-Refresh"] = body["refreshToken"]
        except Exception:
            pass

        if not cookies:
            message = "Login response contains no cookies or tokens"
            body_code = body.get("code", "")
            body_message = body.get("message", "")
            if body_code or body_message:
                message = f"{message}: {body_code} {body_message}".strip()
            raise RuntimeError(message)

        # Build cookie string
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
        return cookie_str

    except requests.RequestException as e:
        raise RuntimeError(f"Login request failed: {e}")


def _get_config_from_skilldeps() -> tuple:
    """Get configuration from SkillDeps-injected environment variables.

    Returns:
        Tuple of (base_url, auth_token, instance_config) or (None, None, None) if not available
    """
    # Read from SkillDeps-injected environment variables
    cookies_json = os.environ.get('ATLASCLAW_COOKIES', '{}')
    provider_config_json = os.environ.get('ATLASCLAW_PROVIDER_CONFIG', '{}')

    cookies = {}
    provider_config = {}

    try:
        cookies = json.loads(cookies_json)
    except json.JSONDecodeError:
        pass

    try:
        provider_config = json.loads(provider_config_json)
    except json.JSONDecodeError:
        pass

    # Get SmartCMP instances from provider config
    smartcmp_instances = provider_config.get('smartcmp', {})

    if not smartcmp_instances:
        if _provider_instance_requested():
            raise ProviderConfigError(
                "ATLASCLAW_PROVIDER_INSTANCE is set, but no SmartCMP provider instances are configured."
            )
        return None, None, None

    instance_name, instance = _select_smartcmp_instance(smartcmp_instances)

    # Extract configuration
    base_url = instance.get('base_url', '')
    explicit_auth_url = instance.get('auth_url', '')
    raw_auth_type = instance.get('auth_type', '')
    if isinstance(raw_auth_type, list):
        auth_type = str(raw_auth_type[0] if raw_auth_type else '').strip()
    else:
        auth_type = str(raw_auth_type or '').strip()

    # Authentication priority for legacy unresolved configs:
    # 1. Request-scoped CloudChef-Authenticate cookie/token
    # 2. Shared provider token from provider config
    # 3. User token from provider config
    # 4. Cookie from provider config
    # 5. Username/Password from provider config
    cloudchef_token = cookies.get('CloudChef-Authenticate', '')
    provider_token = instance.get('provider_token', '')
    user_token = instance.get('user_token', '')
    config_cookie = instance.get('cookie', '')
    username = instance.get('username', '')
    password = instance.get('password', '')

    # Determine auth token
    if auth_type == 'provider_token':
        auth_token = provider_token
    elif auth_type == 'user_token':
        auth_token = user_token
    elif auth_type == 'cookie':
        auth_token = cloudchef_token or config_cookie
    elif auth_type == 'credential':
        auth_token = ''
    else:
        auth_token = cloudchef_token or provider_token or user_token or config_cookie

    # If no token but have credentials, try auto-login
    if not auth_token and username and password and base_url:
        try:
            auth_url = _resolve_auth_url(base_url, explicit_auth_url)
            cookie_str = _auto_login(auth_url, username, password, timeout=get_request_timeout(instance))
            # Extract CloudChef-Authenticate JWT token from cookie string
            for part in cookie_str.split(';'):
                part = part.strip()
                if part.startswith('CloudChef-Authenticate='):
                    auth_token = part.split('=', 1)[1]
                    break
            # Fallback to full cookie string if token not found
            if not auth_token:
                auth_token = cookie_str
        except RuntimeError:
            pass

    if not base_url:
        if _provider_instance_requested():
            raise ProviderConfigError(
                f"SmartCMP provider instance '{instance_name}' is missing required base_url."
            )
        return None, None, None

    # Normalize URL
    base_url = normalize_url(base_url)

    return base_url, auth_token, instance


def _provider_instance_requested() -> bool:
    """Return whether runtime selected a provider instance explicitly."""
    return bool(os.environ.get("ATLASCLAW_PROVIDER_INSTANCE", "").strip())


def _requested_provider_instance_name() -> str:
    """Read the explicitly selected provider instance name from the runtime environment."""
    return os.environ.get("ATLASCLAW_PROVIDER_INSTANCE", "").strip()


def _select_smartcmp_instance(smartcmp_instances: dict) -> tuple[str, dict]:
    """Select the SmartCMP instance, failing closed when runtime selected a missing one."""
    requested_name = _requested_provider_instance_name()
    if requested_name:
        requested_instance = smartcmp_instances.get(requested_name)
        if isinstance(requested_instance, dict):
            instance = dict(requested_instance)
            instance[_config_source_key] = _config_source_skilldeps
            return requested_name, instance
        raise ProviderConfigError(
            f"SmartCMP provider instance '{requested_name}' was explicitly selected but is not configured."
        )

    # Direct/local script execution without an explicit runtime instance keeps the existing default selection.
    instance_name = 'prod' if 'prod' in smartcmp_instances else list(smartcmp_instances.keys())[0]
    instance = smartcmp_instances.get(instance_name, {})
    if not isinstance(instance, dict):
        return instance_name, {}
    selected = dict(instance)
    selected[_config_source_key] = _config_source_skilldeps
    return instance_name, selected


def _get_config_from_env() -> tuple:
    """Get configuration from direct local-script environment variables.

    Returns:
        Tuple of (base_url, auth_token, instance_config) or (None, None, None) if not available
    """
    raw_url = os.environ.get("CMP_URL", "")
    provider_token = os.environ.get("CMP_PROVIDER_TOKEN", "")
    user_token = os.environ.get("CMP_API_TOKEN", "")
    cookie = os.environ.get("CMP_COOKIE", "")
    username = os.environ.get("CMP_USERNAME", "")
    password = os.environ.get("CMP_PASSWORD", "")
    explicit_auth_url = os.environ.get("CMP_AUTH_URL", "")

    if not raw_url:
        return None, None, None

    # If provider or legacy API token is provided, use it directly
    token = provider_token or user_token
    if token:
        base_url = normalize_url(raw_url)
        token_key = 'provider_token' if provider_token else 'user_token'
        instance = {'base_url': raw_url, token_key: token, _config_source_key: _config_source_env}
        return base_url, token, instance

    auth_url = _resolve_auth_url(raw_url, explicit_auth_url)

    # If no explicit cookie, try auto-login
    if not cookie:
        if username and password and auth_url:
            try:
                cookie = _auto_login(auth_url, username, password, timeout=get_request_timeout())
            except RuntimeError:
                pass

    if not cookie:
        return None, None, None

    # Extract CloudChef-Authenticate JWT token for API header use
    auth_token = cookie
    for part in cookie.split(';'):
        part = part.strip()
        if part.startswith('CloudChef-Authenticate='):
            auth_token = part.split('=', 1)[1]
            break

    base_url = normalize_url(raw_url)

    # Build a minimal instance config for direct environment usage.
    instance = {
        'base_url': raw_url,
        'cookie': cookie,
        _config_source_key: _config_source_env,
    }
    if username:
        instance['username'] = username

    return base_url, auth_token, instance


def get_cmp_config(exit_on_error: bool = True) -> tuple:
    """Get SmartCMP configuration from SkillDeps or environment variables.

    Priority:
    1. ATLASCLAW_PROVIDER_CONFIG / ATLASCLAW_COOKIES (from SkillDeps)
    2. Legacy CMP_URL / CMP_COOKIE / CMP_USERNAME / CMP_PASSWORD

    Args:
        exit_on_error: If True, print error and exit when config unavailable

    Returns:
        Tuple of (base_url, auth_token, instance_config)

    Raises:
        SystemExit: When exit_on_error=True and config unavailable
    """
    # Try SkillDeps first
    try:
        base_url, auth_token, instance = _get_config_from_skilldeps()
    except ProviderConfigError as e:
        if exit_on_error:
            print(f"[ERROR] {e}")
            sys.exit(1)
        return "", "", {}

    if _provider_instance_requested() and (not base_url or not auth_token):
        if exit_on_error:
            print("[ERROR] Explicit SmartCMP provider instance is not usable with the current credentials.")
            sys.exit(1)
        return "", "", {}

    # Fall back to legacy environment variables
    if not base_url or not auth_token:
        base_url, auth_token, instance = _get_config_from_env()

    # Final validation
    if not base_url or not auth_token:
        if exit_on_error:
            print("[ERROR] SmartCMP service is unavailable because access authentication is not configured.")
            print("AtlasClaw could not access this provider with the current credentials.")
            print()
            sys.exit(1)
        return "", "", {}

    return base_url, auth_token, instance


def create_headers(auth_token: str, content_type: str = "application/json; charset=utf-8") -> dict:
    """Create standard HTTP headers for SmartCMP API requests.

    Args:
        auth_token: CloudChef-Authenticate token, session cookie, or API token
        content_type: Content-Type header value (default: application/json)

    Returns:
        Dictionary of HTTP headers
    """
    headers = {}
    if auth_token:
        # API tokens (cmp_tk_*) use Authorization: Bearer header
        if auth_token.startswith("cmp_tk_"):
            headers["Authorization"] = f"Bearer {auth_token}"
        else:
            headers["CloudChef-Authenticate"] = auth_token
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def require_config():
    """Validate that configuration is available, exit if not.

    Call this at the start of scripts that require CMP connection.

    Returns:
        Tuple of (base_url, auth_token, headers, instance)
    """
    base_url, auth_token, instance = get_cmp_config(exit_on_error=True)
    headers = create_headers(auth_token)
    return base_url, auth_token, headers, instance


# Convenience: Auto-configure when imported
# Scripts can use: from _common import BASE_URL, AUTH_TOKEN, HEADERS, INSTANCE
BASE_URL, AUTH_TOKEN, INSTANCE = get_cmp_config(exit_on_error=False)
HEADERS = create_headers(AUTH_TOKEN) if AUTH_TOKEN else {}
