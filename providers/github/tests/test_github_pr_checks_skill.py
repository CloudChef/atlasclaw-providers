from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
ATLASCLAW_REPO_ROOT = REPO_ROOT.parent / "atlasclaw"
if str(ATLASCLAW_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(ATLASCLAW_REPO_ROOT))

MODULE_PATH = (
    REPO_ROOT
    / "providers"
    / "github"
    / "skills"
    / "github-pr-checks"
    / "scripts"
    / "handler.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_github_pr_checks_module", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


class FakeClient:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, params=None):
        self.calls.append((url, params))
        if url == "/repos/cloudchef/atlasclaw/pulls/55":
            return SimpleNamespace(
                status_code=200,
                text="ok",
                json=lambda: {"head": {"sha": "abc123"}, "title": "Fix deploy flow"},
            )
        if url == "/repos/cloudchef/atlasclaw/commits/abc123/check-runs":
            return SimpleNamespace(
                status_code=200,
                text="ok",
                json=lambda: {
                    "check_runs": [
                        {
                            "name": "build-and-test",
                            "status": "completed",
                            "conclusion": "success",
                            "html_url": "https://github.com/run/1",
                        },
                        {
                            "name": "deploy",
                            "status": "completed",
                            "conclusion": "failure",
                            "html_url": "https://github.com/run/2",
                        },
                    ]
                },
            )
        if url == "/repos/cloudchef/atlasclaw/commits/abc123/status":
            return SimpleNamespace(
                status_code=200,
                text="ok",
                json=lambda: {
                    "state": "failure",
                    "statuses": [
                        {
                            "context": "lint",
                            "state": "success",
                            "target_url": "https://github.com/status/1",
                        }
                    ],
                },
            )
        raise AssertionError(f"Unexpected GET: {url} {params}")


def test_github_pr_checks_handler_returns_combined_checks(monkeypatch):
    module = load_module()
    fake_client = FakeClient()

    monkeypatch.setattr(
        module,
        "load_github_connection",
        lambda extra: ("https://api.github.com", "github_pat_123"),
    )
    monkeypatch.setattr(module, "create_github_client", lambda base_url, user_token: fake_client)

    ctx = SimpleNamespace(deps=SimpleNamespace(extra={}))

    result = asyncio.run(module.handler(ctx, repo="cloudchef/atlasclaw", pr_number=55))

    assert fake_client.calls == [
        ("/repos/cloudchef/atlasclaw/pulls/55", None),
        ("/repos/cloudchef/atlasclaw/commits/abc123/check-runs", None),
        ("/repos/cloudchef/atlasclaw/commits/abc123/status", None),
    ]
    assert result["is_error"] is False
    assert result["details"]["repo"] == "cloudchef/atlasclaw"
    assert result["details"]["pr_number"] == 55
    assert result["details"]["head_sha"] == "abc123"
    assert len(result["details"]["checks"]) == 3
    assert result["details"]["checks"][1]["name"] == "deploy"
    assert result["details"]["checks"][1]["conclusion"] == "failure"


def test_github_pr_checks_handler_requires_explicit_repo(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "load_github_connection",
        lambda extra: ("https://api.github.com", "github_pat_123"),
    )

    ctx = SimpleNamespace(deps=SimpleNamespace(extra={}))

    result = asyncio.run(module.handler(ctx, repo="", pr_number=55))

    assert result["is_error"] is True
    assert "repo" in result["content"][0]["text"].lower()
