# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "scripts"))

from _github_client import (
    create_github_client,
    load_github_connection,
    load_github_connection_from_env,
    split_repo_full_name,
)
from _tool_result import emit_cli_result, tool_error, tool_text


def _normalize_repo_relative_path(path: str) -> str:
    normalized = str(path or "").strip()
    if not normalized or normalized.startswith("/") or "://" in normalized or ".." in normalized:
        raise RuntimeError("GitHub API query requires a read-only repo-relative path like pulls/55.")
    return normalized


async def handler(
    ctx: Any,
    repo: str,
    path: str,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    deps = getattr(ctx, "deps", None)
    extra = getattr(deps, "extra", None)
    extra_dict = extra if isinstance(extra, dict) else {}
    try:
        base_url, user_token = load_github_connection(extra_dict)
        payload = _fetch_api_query(base_url, user_token, repo, path, params)
    except RuntimeError as exc:
        return tool_error(str(exc))
    return _format_result(payload)


def _fetch_api_query(
    base_url: str,
    user_token: str,
    repo: str,
    path: str,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    normalized_repo = str(repo or "").strip()
    if not normalized_repo:
        raise RuntimeError("GitHub repo is required and must be provided as owner/repo.")

    try:
        owner, name = split_repo_full_name(normalized_repo)
        normalized_path = _normalize_repo_relative_path(path)
    except RuntimeError as exc:
        raise RuntimeError(str(exc))

    with create_github_client(base_url, user_token) as client:
        resp = client.get(
            f"/repos/{owner}/{name}/{normalized_path}",
            params=params,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"GitHub API query failed: {resp.status_code} {resp.text[:300]}"
            )
        payload = resp.json()

    return {"repo": normalized_repo, "path": normalized_path, "data": payload}


def _format_result(payload: dict[str, Any]) -> dict[str, Any]:
    return tool_text(
        f"GitHub API query returned data for {payload['repo']}/{payload['path']}.",
        details=payload,
    )


def _load_params_from_env() -> Optional[dict[str, Any]]:
    raw = str(os.environ.get("PARAMS", "") or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = ast.literal_eval(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("GitHub API query PARAMS must decode to a JSON object.")
    return parsed


def main(argv: list[str] | None = None) -> int:
    _ = argv
    try:
        base_url, user_token = load_github_connection_from_env()
        repo = str(os.environ.get("REPO", "") or "").strip()
        path = str(os.environ.get("PATH", "") or "").strip()
        params = _load_params_from_env()
        result = _format_result(_fetch_api_query(base_url, user_token, repo, path, params))
    except (RuntimeError, ValueError, SyntaxError) as exc:
        result = tool_error(str(exc))
    return emit_cli_result(result)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
