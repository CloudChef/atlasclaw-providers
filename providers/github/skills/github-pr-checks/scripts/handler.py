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


def _fetch_checks(base_url: str, user_token: str, repo: str, pr_number: int) -> dict[str, Any]:
    normalized_repo = str(repo or "").strip()
    if not normalized_repo:
        raise RuntimeError("GitHub repo is required and must be provided as owner/repo.")

    owner, name = split_repo_full_name(normalized_repo)

    with create_github_client(base_url, user_token) as client:
        pr_resp = client.get(f"/repos/{owner}/{name}/pulls/{int(pr_number)}")
        if pr_resp.status_code != 200:
            raise RuntimeError(
                f"GitHub PR lookup failed: {pr_resp.status_code} {pr_resp.text[:300]}"
            )
        pr_payload = pr_resp.json()
        head_sha = str(((pr_payload.get("head") or {}).get("sha")) or "").strip()
        if not head_sha:
            raise RuntimeError("GitHub PR lookup returned no head SHA.")

        checks_resp = client.get(f"/repos/{owner}/{name}/commits/{head_sha}/check-runs")
        if checks_resp.status_code != 200:
            raise RuntimeError(
                f"GitHub check-runs lookup failed: {checks_resp.status_code} {checks_resp.text[:300]}"
            )
        status_resp = client.get(f"/repos/{owner}/{name}/commits/{head_sha}/status")
        if status_resp.status_code != 200:
            raise RuntimeError(
                f"GitHub commit status lookup failed: {status_resp.status_code} {status_resp.text[:300]}"
            )

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

    return {
        "repo": normalized_repo,
        "pr_number": int(pr_number),
        "head_sha": head_sha,
        "checks": checks,
    }


def _format_result(payload: dict[str, Any]) -> dict[str, Any]:
    summary = [
        f"PR #{payload['pr_number']} checks for {payload['repo']}:",
    ]
    for item in payload["checks"]:
        summary.append(f"- {item['name']}: {item['conclusion'] or item['status']}")

    return tool_text(
        "\n".join(summary),
        details=payload,
    )


def _ctx_extra(ctx: Any) -> dict[str, Any]:
    deps = getattr(ctx, "deps", None)
    extra = getattr(deps, "extra", None)
    return extra if isinstance(extra, dict) else {}


async def handler(ctx: Any, repo: str, pr_number: int) -> dict[str, Any]:
    try:
        base_url, user_token = load_github_connection(_ctx_extra(ctx))
        payload = _fetch_checks(base_url, user_token, repo, pr_number)
    except RuntimeError as exc:
        return tool_error(str(exc))
    return _format_result(payload)


def main(argv: list[str] | None = None) -> int:
    _ = argv
    try:
        base_url, user_token = load_github_connection_from_env()
        repo = str(os.environ.get("REPO", "") or "").strip()
        pr_number = int(str(os.environ.get("PR_NUMBER", "") or "").strip())
        result = _format_result(_fetch_checks(base_url, user_token, repo, pr_number))
    except RuntimeError as exc:
        result = tool_error(str(exc))
    except ValueError:
        result = tool_error("GitHub PR checks require PR_NUMBER to be an integer.")
    return emit_cli_result(result)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
