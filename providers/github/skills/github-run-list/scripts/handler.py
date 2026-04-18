# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "scripts"))

from pydantic_ai import RunContext

from app.atlasclaw.core.deps import SkillDeps
from app.atlasclaw.skills.registry import SkillMetadata
from app.atlasclaw.tools.base import ToolResult

from _github_client import create_github_client, load_github_connection, split_repo_full_name


SKILL_METADATA = SkillMetadata(
    name="github_run_list",
    description="List recent GitHub Actions workflow runs for a repository.",
    category="provider:github",
    provider_type="github",
    instance_required=True,
    location="provider",
    source="provider",
    group_ids=["github", "runs"],
    capability_class="provider:github",
    priority=105,
    result_mode="tool_only_ok",
)


async def handler(ctx: RunContext[SkillDeps], repo: str, limit: int = 10) -> dict:
    normalized_repo = str(repo or "").strip()
    if not normalized_repo:
        return ToolResult.error("GitHub repo is required and must be provided as owner/repo.").to_dict()

    try:
        owner, name = split_repo_full_name(normalized_repo)
    except RuntimeError as exc:
        return ToolResult.error(str(exc)).to_dict()

    extra = ctx.deps.extra if isinstance(ctx.deps.extra, dict) else {}
    base_url, user_token = load_github_connection(extra)
    bounded_limit = max(1, min(int(limit), 20))

    with create_github_client(base_url, user_token) as client:
        resp = client.get(
            f"/repos/{owner}/{name}/actions/runs",
            params={"per_page": bounded_limit, "page": 1},
        )
        if resp.status_code != 200:
            return ToolResult.error(
                f"GitHub workflow run listing failed: {resp.status_code} {resp.text[:300]}"
            ).to_dict()
        payload = resp.json() or {}

    runs = [
        {
            "run_id": int(item.get("id")),
            "name": str(item.get("name", "")),
            "status": str(item.get("status", "")),
            "conclusion": str(item.get("conclusion", "")),
            "head_branch": str(item.get("head_branch", "")),
            "url": str(item.get("html_url", "")),
        }
        for item in payload.get("workflow_runs", [])
        if item.get("id") is not None
    ]

    lines = [f"Recent workflow runs for {normalized_repo}:"]
    for item in runs:
        lines.append(f"- {item['run_id']}: {item['name']} [{item['conclusion'] or item['status']}]")

    return ToolResult.text(
        "\n".join(lines),
        details={"repo": normalized_repo, "runs": runs},
    ).to_dict()
