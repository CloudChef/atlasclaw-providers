# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PROVIDER_ROOT = REPO_ROOT / "providers" / "github"


def test_github_provider_package_layout() -> None:
    assert (PROVIDER_ROOT / "PROVIDER.md").is_file()
    assert (PROVIDER_ROOT / "README.md").is_file()
    assert (PROVIDER_ROOT / "skills" / "github" / "SKILL.md").is_file()
    assert (PROVIDER_ROOT / "skills" / "github" / "scripts" / "github_cli.py").is_file()


def test_github_provider_metadata_declares_user_token_auth() -> None:
    provider_text = (PROVIDER_ROOT / "PROVIDER.md").read_text(encoding="utf-8")
    skill_text = (PROVIDER_ROOT / "skills" / "github" / "SKILL.md").read_text(encoding="utf-8")

    assert "provider_type: github" in provider_text
    assert "auth_type" in provider_text
    assert "user_token" in provider_text
    assert 'provider_type: "github"' in skill_text
    assert 'instance_required: "true"' in skill_text
    assert 'tool_cli_name: "github_cli"' in skill_text
    assert "scripts/github_cli.py:github_cli_handler" in skill_text


def test_legacy_global_github_skill_removed() -> None:
    assert not (REPO_ROOT / "skills" / "github-1.0.0").exists()
