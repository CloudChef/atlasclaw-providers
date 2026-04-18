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
    / "github-run-list"
    / "scripts"
    / "handler.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_github_run_list_module", MODULE_PATH)
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


def test_github_run_list_handler_returns_recent_runs(monkeypatch):
    module = load_module()
    fake_client = FakeClient(
        {
            "workflow_runs": [
                {
                    "id": 101,
                    "name": "build.yml",
                    "status": "completed",
                    "conclusion": "success",
                    "head_branch": "main",
                    "html_url": "https://github.com/run/101",
                },
                {
                    "id": 102,
                    "name": "deploy.yml",
                    "status": "completed",
                    "conclusion": "failure",
                    "head_branch": "main",
                    "html_url": "https://github.com/run/102",
                },
            ]
        }
    )

    monkeypatch.setattr(
        module,
        "load_github_connection",
        lambda extra: ("https://api.github.com", "github_pat_123"),
    )
    monkeypatch.setattr(module, "create_github_client", lambda base_url, user_token: fake_client)

    ctx = SimpleNamespace(deps=SimpleNamespace(extra={}))

    result = asyncio.run(module.handler(ctx, repo="cloudchef/atlasclaw", limit=2))

    assert fake_client.calls == [
        ("/repos/cloudchef/atlasclaw/actions/runs", {"per_page": 2, "page": 1})
    ]
    assert result["is_error"] is False
    assert result["details"]["repo"] == "cloudchef/atlasclaw"
    assert result["details"]["runs"][1]["run_id"] == 102
    assert result["details"]["runs"][1]["conclusion"] == "failure"


def test_github_run_list_handler_requires_explicit_repo(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "load_github_connection",
        lambda extra: ("https://api.github.com", "github_pat_123"),
    )

    ctx = SimpleNamespace(deps=SimpleNamespace(extra={}))

    result = asyncio.run(module.handler(ctx, repo="", limit=5))

    assert result["is_error"] is True
    assert "repo" in result["content"][0]["text"].lower()
