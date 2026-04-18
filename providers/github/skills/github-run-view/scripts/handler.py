# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "scripts"))

from _github_client import (
    create_github_client,
    load_github_connection,
    load_github_connection_from_env,
    split_repo_full_name,
)
from _tool_result import emit_cli_result, tool_error, tool_text


def _fetch_run_view(base_url: str, user_token: str, repo: str, run_id: int) -> dict[str, Any]:
    normalized_repo = str(repo or "").strip()
    if not normalized_repo:
        raise RuntimeError("GitHub repo is required and must be provided as owner/repo.")

    owner, name = split_repo_full_name(normalized_repo)
    normalized_run_id = int(run_id)

    with create_github_client(base_url, user_token) as client:
        run_resp = client.get(f"/repos/{owner}/{name}/actions/runs/{normalized_run_id}")
        if run_resp.status_code != 200:
            raise RuntimeError(
                f"GitHub run lookup failed: {run_resp.status_code} {run_resp.text[:300]}"
            )
        jobs_resp = client.get(
            f"/repos/{owner}/{name}/actions/runs/{normalized_run_id}/jobs",
            params={"per_page": 100, "page": 1},
        )
        if jobs_resp.status_code != 200:
            raise RuntimeError(
                f"GitHub run jobs lookup failed: {jobs_resp.status_code} {jobs_resp.text[:300]}"
            )

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

    return {
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
    }


def _format_result(payload: dict[str, Any]) -> dict[str, Any]:
    run = payload["run"]
    lines = [
        f"Workflow run {run['run_id']} for {payload['repo']}:",
        f"- name: {run['name']}",
        f"- conclusion: {run['conclusion'] or run['status']}",
    ]
    for job in payload["jobs"]:
        suffix = ""
        if job["failed_steps"]:
            suffix = f" | failed steps: {', '.join(job['failed_steps'])}"
        lines.append(f"- job {job['name']}: {job['conclusion']}{suffix}")
    return tool_text("\n".join(lines), details=payload)


def _ctx_extra(ctx: Any) -> dict[str, Any]:
    deps = getattr(ctx, "deps", None)
    extra = getattr(deps, "extra", None)
    return extra if isinstance(extra, dict) else {}


async def handler(ctx: Any, repo: str, run_id: int) -> dict[str, Any]:
    try:
        base_url, user_token = load_github_connection(_ctx_extra(ctx))
        payload = _fetch_run_view(base_url, user_token, repo, run_id)
    except RuntimeError as exc:
        return tool_error(str(exc))
    return _format_result(payload)


def main(argv: list[str] | None = None) -> int:
    _ = argv
    try:
        base_url, user_token = load_github_connection_from_env()
        repo = str(os.environ.get("REPO", "") or "").strip()
        run_id = int(str(os.environ.get("RUN_ID", "") or "").strip())
        result = _format_result(_fetch_run_view(base_url, user_token, repo, run_id))
    except RuntimeError as exc:
        result = tool_error(str(exc))
    except ValueError:
        result = tool_error("GitHub run view requires RUN_ID to be an integer.")
    return emit_cli_result(result)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
