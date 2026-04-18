# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

import httpx


def _pick_provider_instance(extra: dict[str, Any], provider_type: str) -> tuple[str, dict[str, Any]]:
    provider_instances = extra.get("provider_instances", {}) if isinstance(extra, dict) else {}
    if not isinstance(provider_instances, dict):
        provider_instances = {}

    by_type = provider_instances.get(provider_type, {})
    if not isinstance(by_type, dict):
        by_type = {}

    selected_type = str(extra.get("provider_type", "")) if isinstance(extra, dict) else ""
    selected_name = str(extra.get("provider_instance_name", "")) if isinstance(extra, dict) else ""
    selected_cfg = extra.get("provider_instance") if isinstance(extra, dict) else None

    if selected_cfg and isinstance(selected_cfg, dict):
        if selected_type == provider_type and selected_name:
            return selected_name, selected_cfg
        return selected_name or "selected", selected_cfg

    if selected_type == provider_type and selected_name and selected_name in by_type:
        cfg = by_type[selected_name]
        if isinstance(cfg, dict):
            return selected_name, cfg

    if by_type:
        first_name = next(iter(by_type.keys()))
        cfg = by_type.get(first_name)
        if isinstance(cfg, dict):
            return first_name, cfg

    raise RuntimeError(
        f"Provider '{provider_type}' has no configured instances in SkillDeps.extra.provider_instances"
    )


def build_github_headers(user_token: str) -> dict[str, str]:
    token = str(user_token or "").strip()
    if not token:
        raise RuntimeError("GitHub provider config missing required field: user_token")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def load_github_connection(extra: dict[str, Any]) -> tuple[str, str]:
    _, provider_instance = _pick_provider_instance(extra, "github")

    base_url = str(provider_instance.get("base_url", "https://api.github.com")).rstrip("/")
    user_token = str(provider_instance.get("user_token", "")).strip()

    if not user_token:
        raise RuntimeError("GitHub provider config missing required field: user_token")

    return base_url or "https://api.github.com", user_token


def split_repo_full_name(repo: str) -> tuple[str, str]:
    normalized = str(repo or "").strip().strip("/")
    if normalized.count("/") != 1:
        raise RuntimeError("GitHub repo must be provided as owner/repo")
    owner, name = normalized.split("/", 1)
    if not owner or not name:
        raise RuntimeError("GitHub repo must be provided as owner/repo")
    return owner, name


def create_github_client(base_url: str, user_token: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url.rstrip("/"),
        headers=build_github_headers(user_token),
        timeout=30.0,
        proxy=None,
        trust_env=False,
    )
