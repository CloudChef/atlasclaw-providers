# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "scripts"))

from pydantic_ai import RunContext

from app.atlasclaw.core.deps import SkillDeps
from app.atlasclaw.skills.registry import SkillMetadata
from app.atlasclaw.tools.base import ToolResult

from _github_client import create_github_client, load_github_connection, split_repo_full_name


SKILL_METADATA = SkillMetadata(
    name="github_api_query",
    description="Query approved read-only repository-scoped GitHub REST API paths.",
    category="provider:github",
    provider_type="github",
    instance_required=True,
    location="provider",
    source="provider",
    group_ids=["github", "api"],
    capability_class="provider:github",
    priority=120,
    result_mode="tool_only_ok",
)


def _normalize_repo_relative_path(path: str) -> str:
    normalized = str(path or "").strip()
    if not normalized or normalized.startswith("/") or "://" in normalized or ".." in normalized:
        raise RuntimeError("GitHub API query requires a read-only repo-relative path like pulls/55.")
    return normalized


async def handler(
    ctx: RunContext[SkillDeps],
    repo: str,
    path: str,
    params: Optional[dict[str, Any]] = None,
) -> dict:
    normalized_repo = str(repo or "").strip()
    if not normalized_repo:
        return ToolResult.error("GitHub repo is required and must be provided as owner/repo.").to_dict()

    try:
        owner, name = split_repo_full_name(normalized_repo)
        normalized_path = _normalize_repo_relative_path(path)
    except RuntimeError as exc:
        return ToolResult.error(str(exc)).to_dict()

    extra = ctx.deps.extra if isinstance(ctx.deps.extra, dict) else {}
    base_url, user_token = load_github_connection(extra)

    with create_github_client(base_url, user_token) as client:
        resp = client.get(
            f"/repos/{owner}/{name}/{normalized_path}",
            params=params,
        )
        if resp.status_code != 200:
            return ToolResult.error(
                f"GitHub API query failed: {resp.status_code} {resp.text[:300]}"
            ).to_dict()
        payload = resp.json()

    return ToolResult.text(
        f"GitHub API query returned data for {normalized_repo}/{normalized_path}.",
        details={"repo": normalized_repo, "path": normalized_path, "data": payload},
    ).to_dict()
