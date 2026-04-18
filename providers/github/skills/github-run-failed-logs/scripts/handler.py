# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "scripts"))

from pydantic_ai import RunContext

from app.atlasclaw.core.deps import SkillDeps
from app.atlasclaw.skills.registry import SkillMetadata
from app.atlasclaw.tools.base import ToolResult

from _github_client import create_github_client, load_github_connection, split_repo_full_name


SKILL_METADATA = SkillMetadata(
    name="github_run_failed_logs",
    description="Return failed GitHub Actions log excerpts for a workflow run.",
    category="provider:github",
    provider_type="github",
    instance_required=True,
    location="provider",
    source="provider",
    group_ids=["github", "runs"],
    capability_class="provider:github",
    priority=115,
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
        jobs_resp = client.get(
            f"/repos/{owner}/{name}/actions/runs/{normalized_run_id}/jobs",
            params={"per_page": 100, "page": 1},
        )
        if jobs_resp.status_code != 200:
            return ToolResult.error(
                f"GitHub run jobs lookup failed: {jobs_resp.status_code} {jobs_resp.text[:300]}"
            ).to_dict()
        logs_resp = client.get(
            f"/repos/{owner}/{name}/actions/runs/{normalized_run_id}/logs",
            follow_redirects=True,
        )
        if logs_resp.status_code != 200:
            return ToolResult.error(
                f"GitHub run logs lookup failed: {logs_resp.status_code} {logs_resp.text[:300]}"
            ).to_dict()

        jobs_payload = jobs_resp.json() or {}
        archive_bytes = getattr(logs_resp, "content", b"")

    failed_job_names = {
        str(job.get("name", "")).strip()
        for job in jobs_payload.get("jobs", [])
        if str(job.get("conclusion", "")).lower() == "failure"
    }

    failed_logs = []
    with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
        for member in archive.namelist():
            for job_name in failed_job_names:
                if member.startswith(f"{job_name}/"):
                    text = archive.read(member).decode("utf-8", errors="replace")
                    failed_logs.append(
                        {
                            "job_name": job_name,
                            "log_file": member,
                            "excerpt": text[:4000],
                        }
                    )
                    break

    if not failed_logs:
        return ToolResult.text(
            f"No failed log excerpts found for workflow run {normalized_run_id}.",
            details={"repo": normalized_repo, "failed_logs": []},
        ).to_dict()

    return ToolResult.text(
        f"Collected failed log excerpts for workflow run {normalized_run_id} in {normalized_repo}.",
        details={"repo": normalized_repo, "failed_logs": failed_logs},
    ).to_dict()
