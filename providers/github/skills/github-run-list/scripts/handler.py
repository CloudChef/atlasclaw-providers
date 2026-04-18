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


def _bounded_limit(limit: int) -> int:
    return max(1, min(int(limit), 20))


def _fetch_runs(base_url: str, user_token: str, repo: str, limit: int) -> dict[str, Any]:
    normalized_repo = str(repo or "").strip()
    if not normalized_repo:
        raise RuntimeError("GitHub repo is required and must be provided as owner/repo.")

    owner, name = split_repo_full_name(normalized_repo)

    with create_github_client(base_url, user_token) as client:
        resp = client.get(
            f"/repos/{owner}/{name}/actions/runs",
            params={"per_page": _bounded_limit(limit), "page": 1},
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"GitHub workflow run listing failed: {resp.status_code} {resp.text[:300]}"
            )
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

    return {"repo": normalized_repo, "runs": runs}


def _format_result(payload: dict[str, Any]) -> dict[str, Any]:
    lines = [f"Recent workflow runs for {payload['repo']}:"]
    for item in payload["runs"]:
        lines.append(f"- {item['run_id']}: {item['name']} [{item['conclusion'] or item['status']}]")

    return tool_text(
        "\n".join(lines),
        details=payload,
    )


def _ctx_extra(ctx: Any) -> dict[str, Any]:
    deps = getattr(ctx, "deps", None)
    extra = getattr(deps, "extra", None)
    return extra if isinstance(extra, dict) else {}


async def handler(ctx: Any, repo: str, limit: int = 10) -> dict[str, Any]:
    try:
        base_url, user_token = load_github_connection(_ctx_extra(ctx))
        payload = _fetch_runs(base_url, user_token, repo, limit)
    except RuntimeError as exc:
        return tool_error(str(exc))
    return _format_result(payload)


def main(argv: list[str] | None = None) -> int:
    _ = argv
    try:
        base_url, user_token = load_github_connection_from_env()
        repo = str(os.environ.get("REPO", "") or "").strip()
        limit = int(str(os.environ.get("LIMIT", "10") or "10"))
        result = _format_result(_fetch_runs(base_url, user_token, repo, limit))
    except RuntimeError as exc:
        result = tool_error(str(exc))
    except ValueError:
        result = tool_error("GitHub workflow run listing requires LIMIT to be an integer.")
    return emit_cli_result(result)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
