# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "scripts"))

from pydantic_ai import RunContext

from app.atlasclaw.core.deps import SkillDeps
from app.atlasclaw.skills.registry import SkillMetadata
from app.atlasclaw.tools.base import ToolResult

from _github_client import create_github_client, load_github_connection


SKILL_METADATA = SkillMetadata(
    name="github_list_repos",
    description="List recent accessible GitHub repositories for the current user's token.",
    category="provider:github",
    provider_type="github",
    instance_required=True,
    location="provider",
    source="provider",
    group_ids=["github", "repo"],
    capability_class="provider:github",
    priority=90,
    result_mode="tool_only_ok",
)


async def handler(ctx: RunContext[SkillDeps], limit: int = 10) -> dict:
    extra = ctx.deps.extra if isinstance(ctx.deps.extra, dict) else {}
    base_url, user_token = load_github_connection(extra)
    bounded_limit = max(1, min(int(limit), 20))

    with create_github_client(base_url, user_token) as client:
        resp = client.get(
            "/user/repos",
            params={"sort": "updated", "per_page": bounded_limit, "page": 1},
        )
        if resp.status_code != 200:
            return ToolResult.error(
                f"GitHub repository listing failed: {resp.status_code} {resp.text[:300]}"
            ).to_dict()

        payload = resp.json()

    repositories = [
        {
            "repo": str(item.get("full_name", "")),
            "private": bool(item.get("private", False)),
            "default_branch": str(item.get("default_branch", "")),
            "updated_at": str(item.get("updated_at", "")),
        }
        for item in payload
        if str(item.get("full_name", "")).strip()
    ]

    if not repositories:
        return ToolResult.text(
            "No accessible repositories found for the current GitHub token.",
            details={"repositories": []},
        ).to_dict()

    lines = ["Recent accessible repositories:"]
    for item in repositories:
        lines.append(f"- {item['repo']}")

    return ToolResult.text(
        "\n".join(lines),
        details={"repositories": repositories},
    ).to_dict()
