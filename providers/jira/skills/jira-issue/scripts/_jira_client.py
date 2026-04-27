# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

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

    # 1) Explicitly selected instance in current context.
    if selected_cfg and isinstance(selected_cfg, dict):
        if selected_type == provider_type and selected_name:
            return selected_name, selected_cfg
        return selected_name or "selected", selected_cfg

    # 2) Selected instance name/type without inline config -> resolve from provider_instances.
    if selected_type == provider_type and selected_name and selected_name in by_type:
        cfg = by_type[selected_name]
        if isinstance(cfg, dict):
            return selected_name, cfg

    # 3) Default fallback: single instance or first configured instance for the provider.
    if by_type:
        first_name = next(iter(by_type.keys()))
        cfg = by_type.get(first_name)
        if isinstance(cfg, dict):
            return first_name, cfg

    raise RuntimeError(
        f"Provider '{provider_type}' has no configured instances in SkillDeps.extra.provider_instances"
    )


def load_jira_connection(extra: dict[str, Any]) -> tuple[str, str, str, str, str | None]:
    _, provider_instance = _pick_provider_instance(extra, "jira")

    base_url = str(provider_instance.get("base_url", "")).rstrip("/")
    username = str(provider_instance.get("username", ""))
    password = str(provider_instance.get("password", ""))
    api_version = str(provider_instance.get("api_version", "2"))
    default_project = provider_instance.get("default_project")

    if not base_url or not username or not password:
        raise RuntimeError("JIRA provider config missing required fields: base_url/username/password")

    return base_url, username, password, api_version, default_project if isinstance(default_project, str) else None


def create_jira_client(base_url: str, username: str, password: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        auth=(username, password),
        headers={"Content-Type": "application/json"},
        timeout=30.0,
        proxy=None,
        trust_env=False,
    )


def ensure_connection(client: httpx.Client, api_version: str) -> None:
    resp = client.get(f"/rest/api/{api_version}/serverInfo")
    if resp.status_code != 200:
        raise RuntimeError(f"Cannot connect to JIRA: {resp.status_code} {resp.text[:200]}")


def resolve_project_key(client: httpx.Client, api_version: str, default_project: str | None) -> str:
    if default_project:
        return default_project

    resp = client.get(f"/rest/api/{api_version}/project")
    if resp.status_code != 200:
        raise RuntimeError(f"Cannot list projects: {resp.status_code} {resp.text[:200]}")

    projects = resp.json()
    if not projects:
        raise RuntimeError("No JIRA projects available")
    return projects[0]["key"]


def issue_description_to_payload(text: str, api_version: str) -> Any:
    return text
