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
    name="jira_issue_delete",
    description="Delete Jira issue by key via REST API.",
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
        resp = client.delete(f"/rest/api/{api_version}/issue/{issue_key}")
        if resp.status_code not in (200, 204):
            return ToolResult.error(
                f"Delete issue failed: {resp.status_code} {resp.text[:300]}"
            ).to_dict()

        return ToolResult.text(
            f"Deleted issue {issue_key}",
            details={"issue_key": issue_key},
        ).to_dict()
