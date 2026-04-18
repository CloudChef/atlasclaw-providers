# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import os
import sys
import zipfile
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


def _fetch_failed_logs(base_url: str, user_token: str, repo: str, run_id: int) -> dict[str, Any]:
    normalized_repo = str(repo or "").strip()
    if not normalized_repo:
        raise RuntimeError("GitHub repo is required and must be provided as owner/repo.")

    owner, name = split_repo_full_name(normalized_repo)
    normalized_run_id = int(run_id)

    with create_github_client(base_url, user_token) as client:
        jobs_resp = client.get(
            f"/repos/{owner}/{name}/actions/runs/{normalized_run_id}/jobs",
            params={"per_page": 100, "page": 1},
        )
        if jobs_resp.status_code != 200:
            raise RuntimeError(
                f"GitHub run jobs lookup failed: {jobs_resp.status_code} {jobs_resp.text[:300]}"
            )
        logs_resp = client.get(
            f"/repos/{owner}/{name}/actions/runs/{normalized_run_id}/logs",
            follow_redirects=True,
        )
        if logs_resp.status_code != 200:
            raise RuntimeError(
                f"GitHub run logs lookup failed: {logs_resp.status_code} {logs_resp.text[:300]}"
            )

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

    return {"repo": normalized_repo, "run_id": normalized_run_id, "failed_logs": failed_logs}


def _format_result(payload: dict[str, Any]) -> dict[str, Any]:
    failed_logs = payload["failed_logs"]
    if not failed_logs:
        return tool_text(
            f"No failed log excerpts found for workflow run {payload['run_id']}.",
            details={"repo": payload["repo"], "failed_logs": []},
        )
    lines = [f"Failed log excerpts for workflow run {payload['run_id']} in {payload['repo']}:"]
    for item in failed_logs:
        lines.append(f"- {item['job_name']} [{item['log_file']}]")
    return tool_text("\n".join(lines), details={"repo": payload["repo"], "failed_logs": failed_logs})


def _ctx_extra(ctx: Any) -> dict[str, Any]:
    deps = getattr(ctx, "deps", None)
    extra = getattr(deps, "extra", None)
    return extra if isinstance(extra, dict) else {}


async def handler(ctx: Any, repo: str, run_id: int) -> dict[str, Any]:
    try:
        base_url, user_token = load_github_connection(_ctx_extra(ctx))
        payload = _fetch_failed_logs(base_url, user_token, repo, run_id)
    except RuntimeError as exc:
        return tool_error(str(exc))
    return _format_result(payload)


def main(argv: list[str] | None = None) -> int:
    _ = argv
    try:
        base_url, user_token = load_github_connection_from_env()
        repo = str(os.environ.get("REPO", "") or "").strip()
        run_id = int(str(os.environ.get("RUN_ID", "") or "").strip())
        result = _format_result(_fetch_failed_logs(base_url, user_token, repo, run_id))
    except RuntimeError as exc:
        result = tool_error(str(exc))
    except ValueError:
        result = tool_error("GitHub failed-log lookup requires RUN_ID to be an integer.")
    return emit_cli_result(result)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
