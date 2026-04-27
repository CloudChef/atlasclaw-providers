# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pydantic_ai import RunContext

from app.atlasclaw.core.deps import SkillDeps
from app.atlasclaw.skills.registry import SkillMetadata
from app.atlasclaw.tools.base import ToolResult

from _jira_client import ensure_connection, load_jira_connection

import httpx

SKILL_METADATA = SkillMetadata(
    name="jira_issue_get",
    description="Get Jira issue details by key via REST API.",
    category="provider:jira",
    provider_type="jira",
    instance_required=True,
    location="built-in",
)


async def handler(ctx: RunContext[SkillDeps], issue_key: str) -> dict:
    extra = ctx.deps.extra if isinstance(ctx.deps.extra, dict) else {}
    base_url, username, password, api_version, _ = load_jira_connection(extra)

    with httpx.Client(
        base_url=base_url,
        auth=(username, password),
        headers={"Content-Type": "application/json"},
        timeout=30.0,
    ) as client:
        ensure_connection(client, api_version)
        resp = client.get(f"/rest/api/{api_version}/issue/{issue_key}")
        if resp.status_code != 200:
            return ToolResult.error(
                f"Get issue failed: {resp.status_code} {resp.text[:300]}"
            ).to_dict()

        issue = resp.json()
        fields = issue.get("fields", {})
        details = {
            "issue_key": issue.get("key", issue_key),
            "summary": fields.get("summary", ""),
            "status": (fields.get("status") or {}).get("name", ""),
            "issuetype": (fields.get("issuetype") or {}).get("name", ""),
            "priority": (fields.get("priority") or {}).get("name", ""),
        }
        return ToolResult.text(f"Fetched issue {details['issue_key']}", details=details).to_dict()
