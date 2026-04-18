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
    name="github_run_view",
    description="View GitHub Actions workflow run details and failed steps.",
    category="provider:github",
    provider_type="github",
    instance_required=True,
    location="provider",
    source="provider",
    group_ids=["github", "runs"],
    capability_class="provider:github",
    priority=110,
    result_mode="tool_only_ok",
)


async def handler(ctx: RunContext[SkillDeps], repo: str, run_id: int) -> dict:
    normalized_repo = str(repo or "").strip()
    if not normalized_repo:
        return ToolResult.error("GitHub repo is required and must be provided as owner/repo.").to_dict()

    try:
        owner, name = split_repo_full_name(normalized_repo)
    except RuntimeError as exc:
        return ToolResult.error(str(exc)).to_dict()

    extra = ctx.deps.extra if isinstance(ctx.deps.extra, dict) else {}
    base_url, user_token = load_github_connection(extra)
    normalized_run_id = int(run_id)

    with create_github_client(base_url, user_token) as client:
        run_resp = client.get(f"/repos/{owner}/{name}/actions/runs/{normalized_run_id}")
        if run_resp.status_code != 200:
            return ToolResult.error(
                f"GitHub run lookup failed: {run_resp.status_code} {run_resp.text[:300]}"
            ).to_dict()
        jobs_resp = client.get(
            f"/repos/{owner}/{name}/actions/runs/{normalized_run_id}/jobs",
            params={"per_page": 100, "page": 1},
        )
        if jobs_resp.status_code != 200:
            return ToolResult.error(
                f"GitHub run jobs lookup failed: {jobs_resp.status_code} {jobs_resp.text[:300]}"
            ).to_dict()

        run_payload = run_resp.json() or {}
        jobs_payload = jobs_resp.json() or {}

    jobs = []
    for item in jobs_payload.get("jobs", []):
        failed_steps = [
            str(step.get("name", ""))
            for step in item.get("steps", [])
            if str(step.get("conclusion", "")).lower() == "failure"
        ]
        jobs.append(
            {
                "name": str(item.get("name", "")),
                "conclusion": str(item.get("conclusion", "")),
                "failed_steps": failed_steps,
            }
        )

    return ToolResult.text(
        f"Workflow run {normalized_run_id} details for {normalized_repo}.",
        details={
            "repo": normalized_repo,
            "run": {
                "run_id": int(run_payload.get("id", normalized_run_id)),
                "name": str(run_payload.get("name", "")),
                "status": str(run_payload.get("status", "")),
                "conclusion": str(run_payload.get("conclusion", "")),
                "head_branch": str(run_payload.get("head_branch", "")),
                "url": str(run_payload.get("html_url", "")),
            },
            "jobs": jobs,
        },
    ).to_dict()
