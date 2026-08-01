# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Side-effect-free helpers for SmartCMP object-action builders.

Domain action builders and the page Context resolver both import this module.
It must remain free of Provider configuration, authentication, and network
initialization so resolving presentation metadata cannot auto-login.
"""

from __future__ import annotations

from urllib.parse import quote

from app.atlasclaw.core.object_actions import (
    build_agent_prompt_action as build_core_agent_prompt_action,
    build_localized_text as build_core_localized_text,
    build_open_url_action as build_core_open_url_action,
)


def build_ui_hash_href(ui_base_url: str, hash_route: str) -> str:
    """Build an absolute SmartCMP hash-route URL."""
    normalized_base_url = str(ui_base_url or "").strip().rstrip("/")
    if not normalized_base_url:
        return ""
    route = str(hash_route or "").strip()
    if not route.startswith("#/"):
        return ""
    return f"{normalized_base_url}/{route}"


def build_resource_page_href(
    ui_base_url: str,
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
        ui_base_url,
        f"#/main/{normalized_category}/{encoded_resource_id}{suffix}",
    )


def build_object_open_action(
    href: str,
    *,
    action_id: str = "open_detail",
    label_en: str = "Open",
    label_zh: str = "打开",
) -> dict[str, object] | None:
    """Add SmartCMP labels to an AtlasClaw generic navigation action."""

    return build_core_open_url_action(
        action_id,
        href,
        effect="navigate",
        tone="default",
        display_label=_localized_text(label_en, label_zh),
    )


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
    """Add SmartCMP copy to an AtlasClaw generic Agent-prompt action."""

    prompt = _localized_text(prompt_en, prompt_zh)
    confirmation_message = None
    if requires_confirmation and (confirmation_en or confirmation_zh):
        confirmation_message = _localized_text(
            confirmation_en or prompt_en,
            confirmation_zh or prompt_zh,
        )
    return build_core_agent_prompt_action(
        action_id,
        prompt,
        display_label=_localized_text(label_en, label_zh),
        effect=effect,
        tone=tone,
        requires_confirmation=requires_confirmation,
        confirmation_message=confirmation_message,
        prompt_template=prompt_template,
        inputs=inputs,
    )


def _localized_text(default: str, translated: str) -> dict[str, object] | None:
    return build_core_localized_text(
        default,
        {
            "en-US": default,
            "zh-CN": translated,
        },
    )
