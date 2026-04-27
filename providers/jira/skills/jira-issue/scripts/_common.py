# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx


def project_root() -> Path:
    here = Path(__file__).resolve()
    for p in [here] + list(here.parents):
        if (p / "atlasclaw.json").exists():
            return p
    raise RuntimeError("atlasclaw.json not found from script path")


def load_jira_instance() -> dict[str, Any]:
    cfg_path = project_root() / "atlasclaw.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    jira = cfg.get("service_providers", {}).get("jira", {})
    if not isinstance(jira, dict) or not jira:
        raise RuntimeError("service_providers.jira not configured in atlasclaw.json")
    instance_name = next(iter(jira))
    inst = jira[instance_name]
    for key in ("base_url", "username"):
        if not inst.get(key):
            raise RuntimeError(f"missing jira.{instance_name}.{key}")
    if not inst.get("password"):
        raise RuntimeError(f"missing jira.{instance_name}.password")
    return inst


def build_client(inst: dict[str, Any]) -> tuple[httpx.Client, str]:
    api_version = str(inst.get("api_version", "2"))
    client = httpx.Client(
        base_url=str(inst["base_url"]).rstrip("/"),
        auth=(str(inst["username"]), str(inst["password"])),
        headers={"Content-Type": "application/json"},
        timeout=30.0,
        proxy=None,
        trust_env=False,
    )
    return client, api_version


def ensure_connection(client: httpx.Client, api_version: str) -> None:
    resp = client.get(f"/rest/api/{api_version}/serverInfo")
    if resp.status_code != 200:
        raise RuntimeError(f"jira connection failed: {resp.status_code} {resp.text[:200]}")


def _can_create_issue(client: httpx.Client, api_version: str, project_key: str, issue_type: str = "Task") -> bool:
    meta_resp = client.get(
        f"/rest/api/{api_version}/issue/createmeta",
        params={"projectKeys": project_key, "expand": "projects.issuetypes.fields"},
    )
    
    if meta_resp.status_code != 200:
        return True
    
    meta = meta_resp.json()
    for proj in meta.get("projects", []):
        if proj["key"] != project_key:
            continue
        for itype in proj.get("issuetypes", []):
            if itype["name"] != issue_type:
                continue
            for field_key, field_def in itype.get("fields", {}).items():
                if not field_def.get("required"):
                    continue
                if field_key in ("project", "summary", "issuetype", "description", "reporter"):
                    continue
                if field_key == "components":
                    comp_resp = client.get(
                        f"/rest/api/{api_version}/project/{project_key}/components"
                    )
                    if comp_resp.status_code == 200:
                        comps = comp_resp.json()
                        if not comps:
                            return False
    return True


def resolve_project_key(client: httpx.Client, api_version: str, configured: str = "") -> str:
    resp = client.get(f"/rest/api/{api_version}/project")
    if resp.status_code != 200:
        raise RuntimeError(f"cannot list projects: {resp.status_code} {resp.text[:200]}")
    projects = resp.json()
    if not projects:
        raise RuntimeError("no jira project available")
    
    available_keys = {p["key"] for p in projects}
    
    if configured and configured in available_keys:
        if _can_create_issue(client, api_version, configured):
            return configured
    
    for proj in projects:
        key = proj["key"]
        if _can_create_issue(client, api_version, key):
            return key
    
    return projects[0]["key"]


def json_out(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))
