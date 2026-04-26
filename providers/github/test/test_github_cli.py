from __future__ import annotations

import asyncio
import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "github"
    / "scripts"
    / "github_cli.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("github_cli_under_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_ctx(extra: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(deps=SimpleNamespace(extra=extra))


def run_handler(module: Any, ctx: Any, **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(module.github_cli_handler(ctx, **kwargs))


def test_github_dot_com_sets_gh_token(monkeypatch) -> None:
    module = load_module()
    captured: dict[str, Any] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, "checks ok", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    ctx = make_ctx(
        {
            "provider_instances": {
                "github": {
                    "default": {
                        "base_url": "https://api.github.com",
                        "hostname": "github.com",
                        "auth_type": "user_token",
                        "user_token": "github_pat_user_123",
                    }
                }
            }
        }
    )

    result = run_handler(module, ctx, args=["pr", "checks", "55"], repo="owner/repo")

    assert result["success"] is True
    assert captured["cmd"] == ["gh", "pr", "checks", "55"]
    assert captured["env"]["GH_TOKEN"] == "github_pat_user_123"
    assert "GH_ENTERPRISE_TOKEN" not in captured["env"]
    assert captured["env"]["GH_HOST"] == "github.com"
    assert captured["env"]["GH_REPO"] == "owner/repo"
    assert captured["env"]["GH_PROMPT_DISABLED"] == "1"
    assert captured["env"]["GH_CONFIG_DIR"]


def test_enterprise_host_sets_enterprise_token(monkeypatch) -> None:
    module = load_module()
    captured: dict[str, Any] = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, "run list", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    ctx = make_ctx(
        {
            "provider_instances": {
                "github": {
                    "enterprise": {
                        "base_url": "https://github.company.com/api/v3",
                        "hostname": "github.company.com",
                        "auth_type": "user_token",
                        "user_token": "ghp_enterprise123",
                    }
                }
            }
        }
    )

    result = run_handler(module, ctx, args=["run", "list"])

    assert result["success"] is True
    assert "GH_TOKEN" not in captured["env"]
    assert captured["env"]["GH_ENTERPRISE_TOKEN"] == "ghp_enterprise123"
    assert captured["env"]["GH_HOST"] == "github.company.com"
    assert result["provider"]["hostname"] == "github.company.com"


def test_selected_instance_is_used_when_multiple_instances_exist(monkeypatch) -> None:
    module = load_module()
    captured: dict[str, Any] = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, "selected", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    ctx = make_ctx(
        {
            "provider_type": "github",
            "provider_instance_name": "enterprise",
            "provider_instances": {
                "github": {
                    "default": {
                        "hostname": "github.com",
                        "auth_type": "user_token",
                        "user_token": "github_pat_default",
                    },
                    "enterprise": {
                        "hostname": "github.company.com",
                        "auth_type": "user_token",
                        "user_token": "github_pat_enterprise",
                    },
                }
            },
        }
    )

    result = run_handler(module, ctx, args=["api", "user"])

    assert result["success"] is True
    assert captured["env"]["GH_ENTERPRISE_TOKEN"] == "github_pat_enterprise"
    assert result["provider"]["instance_name"] == "enterprise"


def test_missing_user_token_returns_clear_error(monkeypatch) -> None:
    module = load_module()

    def fake_run(*_args, **_kwargs):
        raise AssertionError("subprocess.run should not be called without user_token")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    ctx = make_ctx(
        {
            "provider_instances": {
                "github": {
                    "default": {
                        "hostname": "github.com",
                        "auth_type": "user_token",
                    }
                }
            }
        }
    )

    result = run_handler(module, ctx, args=["api", "user"])

    assert result["success"] is False
    assert "user_token is not configured" in result["error"]


def test_command_output_redacts_tokens(monkeypatch) -> None:
    module = load_module()
    token = "github_pat_secret_1234567890"

    def fake_run(cmd, **_kwargs):
        return subprocess.CompletedProcess(
            cmd,
            1,
            f"stdout leaked {token}",
            f"stderr leaked Authorization: Bearer {token}",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    ctx = make_ctx(
        {
            "provider_instances": {
                "github": {
                    "default": {
                        "hostname": "github.com",
                        "auth_type": "user_token",
                        "user_token": token,
                    }
                }
            }
        }
    )

    result = run_handler(module, ctx, args=["api", "user"])

    assert result["success"] is False
    assert token not in result["output"]
    assert token not in result["error"]
    assert "***" in result["output"]
    assert "Authorization: Bearer ***" in result["error"]
