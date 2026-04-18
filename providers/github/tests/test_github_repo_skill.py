from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[3]
ATLASCLAW_REPO_ROOT = REPO_ROOT.parent / "atlasclaw"
if str(ATLASCLAW_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(ATLASCLAW_REPO_ROOT))

MODULE_PATH = (
    REPO_ROOT
    / "providers"
    / "github"
    / "skills"
    / "github-repo"
    / "scripts"
    / "handler.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_github_repo_skill_module", MODULE_PATH)
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
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, params=None):
        self.calls.append((url, params))
        return SimpleNamespace(
            status_code=200,
            text="ok",
            json=lambda: self._payload,
        )


def test_github_repo_handler_lists_recent_accessible_repositories(monkeypatch):
    module = load_module()
    fake_client = FakeClient(
        [
            {
                "full_name": "cloudchef/atlasclaw",
                "private": True,
                "default_branch": "main",
                "updated_at": "2026-04-18T10:00:00Z",
            },
            {
                "full_name": "cloudchef/atlasclaw-providers",
                "private": True,
                "default_branch": "main",
                "updated_at": "2026-04-17T08:00:00Z",
            },
        ]
    )

    monkeypatch.setattr(
        module,
        "load_github_connection",
        lambda extra: ("https://api.github.com", "github_pat_123"),
    )
    monkeypatch.setattr(module, "create_github_client", lambda base_url, user_token: fake_client)

    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            extra={
                "provider_instances": {
                    "github": {
                        "default": {
                            "base_url": "https://api.github.com",
                            "auth_type": "user_token",
                            "user_token": "github_pat_123",
                        }
                    }
                }
            }
        )
    )

    result = asyncio.run(module.handler(ctx, limit=2))

    assert fake_client.calls == [
        ("/user/repos", {"sort": "updated", "per_page": 2, "page": 1})
    ]
    assert result["is_error"] is False
    assert result["details"]["repositories"] == [
        {
            "repo": "cloudchef/atlasclaw",
            "private": True,
            "default_branch": "main",
            "updated_at": "2026-04-18T10:00:00Z",
        },
        {
            "repo": "cloudchef/atlasclaw-providers",
            "private": True,
            "default_branch": "main",
            "updated_at": "2026-04-17T08:00:00Z",
        },
    ]
    assert "cloudchef/atlasclaw" in result["content"][0]["text"]


def test_github_repo_handler_does_not_invent_a_default_repository(monkeypatch):
    module = load_module()
    fake_client = FakeClient([])

    monkeypatch.setattr(
        module,
        "load_github_connection",
        lambda extra: ("https://api.github.com", "github_pat_123"),
    )
    monkeypatch.setattr(module, "create_github_client", lambda base_url, user_token: fake_client)

    ctx = SimpleNamespace(deps=SimpleNamespace(extra={}))

    result = asyncio.run(module.handler(ctx, limit=5))

    assert result["is_error"] is False
    assert result["details"]["repositories"] == []
    assert "No accessible repositories" in result["content"][0]["text"]
    assert "repo" not in result["details"]
