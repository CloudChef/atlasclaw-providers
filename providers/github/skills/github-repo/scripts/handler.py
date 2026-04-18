# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "scripts"))

from _github_client import create_github_client, load_github_connection, load_github_connection_from_env
from _tool_result import emit_cli_result, tool_error, tool_text


def _bounded_limit(limit: int) -> int:
    return max(1, min(int(limit), 20))


def _fetch_repositories(base_url: str, user_token: str, limit: int) -> list[dict[str, Any]]:
    with create_github_client(base_url, user_token) as client:
        resp = client.get(
            "/user/repos",
            params={"sort": "updated", "per_page": _bounded_limit(limit), "page": 1},
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"GitHub repository listing failed: {resp.status_code} {resp.text[:300]}"
            )

        payload = resp.json()

    return [
        {
            "repo": str(item.get("full_name", "")),
            "private": bool(item.get("private", False)),
            "default_branch": str(item.get("default_branch", "")),
            "updated_at": str(item.get("updated_at", "")),
        }
        for item in payload
        if str(item.get("full_name", "")).strip()
    ]


def _format_result(repositories: list[dict[str, Any]]) -> dict[str, Any]:
    if not repositories:
        return tool_text(
            "No accessible repositories found for the current GitHub token.",
            details={"repositories": []},
        )

    lines = [f"Found {len(repositories)} accessible repositories:", "Recent accessible repositories:"]
    for item in repositories:
        lines.append(f"- {item['repo']}")

    return tool_text(
        "\n".join(lines),
        details={"repositories": repositories},
    )


def _ctx_extra(ctx: Any) -> dict[str, Any]:
    deps = getattr(ctx, "deps", None)
    extra = getattr(deps, "extra", None)
    return extra if isinstance(extra, dict) else {}


async def handler(ctx: Any, limit: int = 10) -> dict[str, Any]:
    try:
        base_url, user_token = load_github_connection(_ctx_extra(ctx))
        repositories = _fetch_repositories(base_url, user_token, limit)
    except RuntimeError as exc:
        return tool_error(str(exc))
    return _format_result(repositories)


def main(argv: list[str] | None = None) -> int:
    _ = argv
    try:
        base_url, user_token = load_github_connection_from_env()
        limit = int(str(os.environ.get("LIMIT", "10") or "10"))
        result = _format_result(_fetch_repositories(base_url, user_token, limit))
    except RuntimeError as exc:
        result = tool_error(str(exc))
    except ValueError:
        result = tool_error("GitHub repo listing requires LIMIT to be an integer.")
    return emit_cli_result(result)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
