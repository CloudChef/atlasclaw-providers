# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Side-effect-free helpers for SmartCMP object-action builders.

Domain action builders and the page Context resolver both import this module.
It must remain free of Provider configuration, authentication, and network
initialization so resolving presentation metadata cannot auto-login.
"""

from __future__ import annotations

from urllib.parse import quote, urlparse, urlunparse


_API_PATH = "/platform-api"


def normalize_ui_base_url(url: str) -> str:
    """Return the browser root for a SmartCMP API or UI URL."""
    normalized = str(url or "").strip()
    if not normalized:
        return ""
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"

    parsed = urlparse(normalized)
    path = parsed.path.rstrip("/")
    if path.endswith(_API_PATH):
        path = path[: -len(_API_PATH)].rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def build_ui_hash_href(ui_base_url: str, hash_route: str) -> str:
    """Build an absolute SmartCMP hash-route URL."""
    normalized_base_url = normalize_ui_base_url(ui_base_url)
    if not normalized_base_url:
        return ""
    route = str(hash_route or "").strip()
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
    """Build the verified SmartCMP page URL for one resource category."""
    encoded_resource_id = quote(str(resource_id or ""), safe="")
    if not encoded_resource_id:
        return ""
    normalized_category = str(category or "virtual-machines").strip("/")
    suffix = "/details" if normalized_category == "virtual-machines" else ""
    return build_ui_hash_href(
        normalize_ui_base_url(base_url),
        f"#/main/{normalized_category}/{encoded_resource_id}{suffix}",
    )


def _localized_text(default: str, *, zh_cn: str) -> dict[str, object]:
    return {
        "default": str(default or "").strip(),
        "translations": {
            "en-US": str(default or "").strip(),
            "zh-CN": str(zh_cn or "").strip(),
        },
    }


def build_object_open_action(
    href: str,
    *,
    action_id: str = "open_detail",
    label_en: str = "Open",
    label_zh: str = "打开",
) -> dict[str, object] | None:
    """Build one navigation action for a verified object URL."""
    normalized_href = str(href or "").strip()
    if not normalized_href:
        return None
    return {
        "action_id": str(action_id or "open_detail"),
        "kind": "open_url",
        "display_label": _localized_text(label_en, zh_cn=label_zh),
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
    """Build one generic Agent prompt action without Provider side effects."""
    normalized_action_id = str(action_id or "").strip()
    if not normalized_action_id or not str(prompt_en or "").strip() or not str(prompt_zh or "").strip():
        return None
    action: dict[str, object] = {
        "action_id": normalized_action_id,
        "kind": "agent_prompt",
        "display_label": _localized_text(label_en, zh_cn=label_zh),
        "effect": str(effect or "read"),
        "tone": str(tone or "default"),
    }
    prompt_key = "agent_prompt_template" if prompt_template else "agent_prompt"
    action[prompt_key] = _localized_text(prompt_en, zh_cn=prompt_zh)
    if requires_confirmation:
        action["requires_confirmation"] = True
        if confirmation_en or confirmation_zh:
            action["confirmation_message"] = _localized_text(
                confirmation_en or prompt_en,
                zh_cn=confirmation_zh or prompt_zh,
            )
    if inputs:
        action["inputs"] = list(inputs)
    return action
