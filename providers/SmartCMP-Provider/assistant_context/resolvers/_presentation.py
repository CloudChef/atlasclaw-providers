# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Pure Provider presentation helpers for SmartCMP Context resolvers."""

from __future__ import annotations

def localized_text(
    default: str,
    *,
    zh_cn: str,
    en_us: str | None = None,
) -> dict[str, object]:
    """Build the locale envelope consumed by AtlasClaw's generic action renderer."""
    default_text = str(default or "").strip()
    en_text = str(en_us if en_us is not None else default_text).strip()
    return {
        "default": default_text,
        "translations": {
            "en-US": en_text,
            "zh-CN": str(zh_cn or "").strip(),
        },
    }


def build_open_action(
    href: str,
    *,
    action_id: str = "open_detail",
    label_en: str = "Open",
    label_zh: str = "打开",
) -> dict[str, object] | None:
    """Build one generic browser-navigation action for a verified object URL."""
    normalized_href = str(href or "").strip()
    if not normalized_href:
        return None
    return {
        "action_id": str(action_id or "open_detail"),
        "kind": "open_url",
        "display_label": localized_text(label_en, zh_cn=label_zh),
        "href": normalized_href,
        "effect": "navigate",
        "tone": "default",
    }


def build_prompt_action(
    action_id: str,
    *,
    label_en: str,
    label_zh: str,
    prompt_en: str,
    prompt_zh: str,
    effect: str = "read",
    tone: str = "default",
    prompt_template: bool = False,
    inputs: list[dict[str, object]] | None = None,
    requires_confirmation: bool = False,
    confirmation_message_en: str = "",
    confirmation_message_zh: str = "",
) -> dict[str, object] | None:
    """Build one generic agent-prompt action while preserving the public action schema."""
    normalized_action_id = str(action_id or "").strip()
    if (
        not normalized_action_id
        or not str(prompt_en or "").strip()
        or not str(prompt_zh or "").strip()
    ):
        return None
    action: dict[str, object] = {
        "action_id": normalized_action_id,
        "kind": "agent_prompt",
        "display_label": localized_text(label_en, zh_cn=label_zh),
        "effect": str(effect or "read"),
        "tone": str(tone or "default"),
    }
    prompt_key = "agent_prompt_template" if prompt_template else "agent_prompt"
    action[prompt_key] = localized_text(prompt_en, zh_cn=prompt_zh)
    if inputs:
        action["inputs"] = inputs
    if requires_confirmation:
        if (
            not str(confirmation_message_en or "").strip()
            or not str(confirmation_message_zh or "").strip()
        ):
            return None
        action["requires_confirmation"] = True
        action["confirmation_message"] = localized_text(
            confirmation_message_en,
            zh_cn=confirmation_message_zh,
        )
    return action
