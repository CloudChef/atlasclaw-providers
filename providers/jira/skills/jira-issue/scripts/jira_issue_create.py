# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import sys
from pathlib import Path

# Add scripts directory to path for local imports
sys.path.insert(0, str(Path(__file__).parent))

from pydantic_ai import RunContext

from app.atlasclaw.core.deps import SkillDeps
from app.atlasclaw.skills.registry import SkillMetadata
from app.atlasclaw.tools.base import ToolResult

from _jira_client import (
    create_jira_client,
    ensure_connection,
    issue_description_to_payload,
    load_jira_connection,
    resolve_project_key,
)

SKILL_METADATA = SkillMetadata(
    name="jira_issue_create",
    description="Create a Jira issue via REST API.",
    category="provider:jira",
    provider_type="jira",
    instance_required=True,
    location="built-in",
)


async def handler(
    ctx: RunContext[SkillDeps],
    summary: str,
    description: str,
    issue_type: str = "Task",
    project_key: str = "",
    priority: str = "",
) -> dict:
    extra = ctx.deps.extra if isinstance(ctx.deps.extra, dict) else {}
    
    base_url, username, password, api_version, default_project = load_jira_connection(extra)

    with create_jira_client(base_url, username, password) as client:
        ensure_connection(client, api_version)
        target_project = project_key or resolve_project_key(client, api_version, default_project)

        # Build base fields
        fields: dict = {
            "project": {"key": target_project},
            "summary": summary,
            "description": issue_description_to_payload(description, api_version),
            "issuetype": {"name": issue_type},
        }
        if priority:
            fields["priority"] = {"name": priority}

        # Auto-detect and fill required fields
        fields = _fill_required_fields(client, api_version, target_project, issue_type, fields)

        resp = client.post(f"/rest/api/{api_version}/issue", json={"fields": fields})
        if resp.status_code not in (200, 201):
            return ToolResult.error(
                f"Create issue failed: {resp.status_code} {resp.text[:300]}"
            ).to_dict()

        data = resp.json()
        issue_key = data.get("key", "")
        issue_id = data.get("id", "")
        return ToolResult.text(
            f"Created issue {issue_key}",
            details={"issue_key": issue_key, "issue_id": issue_id, "project_key": target_project},
        ).to_dict()


def _fill_required_fields(
    client,
    api_version: str,
    project_key: str,
    issue_type: str,
    fields: dict,
) -> dict:
    """Auto-detect and fill required fields for the issue."""
    # Get create metadata
    meta_resp = client.get(
        f"/rest/api/{api_version}/issue/createmeta",
        params={"projectKeys": project_key, "expand": "projects.issuetypes.fields"},
    )
    
    if meta_resp.status_code != 200:
        return fields
    
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
                if field_key in fields:
                    continue
                if field_key in ("project", "summary", "issuetype", "description", "reporter"):
                    continue
                
                # Handle components field
                if field_key == "components":
                    comp_resp = client.get(f"/rest/api/{api_version}/project/{project_key}/components")
                    if comp_resp.status_code == 200:
                        comps = comp_resp.json()
                        if comps:
                            fields["components"] = [{"id": comps[0]["id"]}]
                
                # Handle priority field
                elif field_key == "priority":
                    fields.setdefault("priority", {"name": "Medium"})
    
    return fields
