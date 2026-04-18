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
    name="github_pr_checks",
    description="Inspect CI checks for a GitHub pull request.",
    category="provider:github",
    provider_type="github",
    instance_required=True,
    location="provider",
    source="provider",
    group_ids=["github", "checks"],
    capability_class="provider:github",
    priority=100,
    result_mode="tool_only_ok",
)


async def handler(ctx: RunContext[SkillDeps], repo: str, pr_number: int) -> dict:
    normalized_repo = str(repo or "").strip()
    if not normalized_repo:
        return ToolResult.error("GitHub repo is required and must be provided as owner/repo.").to_dict()

    try:
        owner, name = split_repo_full_name(normalized_repo)
    except RuntimeError as exc:
        return ToolResult.error(str(exc)).to_dict()

    extra = ctx.deps.extra if isinstance(ctx.deps.extra, dict) else {}
    base_url, user_token = load_github_connection(extra)

    with create_github_client(base_url, user_token) as client:
        pr_resp = client.get(f"/repos/{owner}/{name}/pulls/{int(pr_number)}")
        if pr_resp.status_code != 200:
            return ToolResult.error(
                f"GitHub PR lookup failed: {pr_resp.status_code} {pr_resp.text[:300]}"
            ).to_dict()
        pr_payload = pr_resp.json()
        head_sha = str(((pr_payload.get("head") or {}).get("sha")) or "").strip()
        if not head_sha:
            return ToolResult.error("GitHub PR lookup returned no head SHA.").to_dict()

        checks_resp = client.get(f"/repos/{owner}/{name}/commits/{head_sha}/check-runs")
        if checks_resp.status_code != 200:
            return ToolResult.error(
                f"GitHub check-runs lookup failed: {checks_resp.status_code} {checks_resp.text[:300]}"
            ).to_dict()
        status_resp = client.get(f"/repos/{owner}/{name}/commits/{head_sha}/status")
        if status_resp.status_code != 200:
            return ToolResult.error(
                f"GitHub commit status lookup failed: {status_resp.status_code} {status_resp.text[:300]}"
            ).to_dict()

        check_runs = (checks_resp.json() or {}).get("check_runs", [])
        combined_status = status_resp.json() or {}

    checks = []
    for item in check_runs:
        checks.append(
            {
                "name": str(item.get("name", "")),
                "status": str(item.get("status", "")),
                "conclusion": str(item.get("conclusion", "")),
                "url": str(item.get("html_url", "")),
            }
        )

    for item in combined_status.get("statuses", []):
        checks.append(
            {
                "name": str(item.get("context", "")),
                "status": str(item.get("state", "")),
                "conclusion": str(item.get("state", "")),
                "url": str(item.get("target_url", "")),
            }
        )

    summary = [
        f"PR #{int(pr_number)} checks for {normalized_repo}:",
    ]
    for item in checks:
        summary.append(f"- {item['name']}: {item['conclusion'] or item['status']}")

    return ToolResult.text(
        "\n".join(summary),
        details={
            "repo": normalized_repo,
            "pr_number": int(pr_number),
            "head_sha": head_sha,
            "checks": checks,
        },
    ).to_dict()
