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
    / "github-api-query"
    / "scripts"
    / "handler.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_github_api_query_module", MODULE_PATH)
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
        return SimpleNamespace(
            status_code=200,
            text="ok",
            json=lambda: {"title": "Fix deploy flow", "state": "open", "user": {"login": "gangw"}},
        )


def test_github_api_query_handler_reads_repo_scoped_rest_path(monkeypatch):
    module = load_module()
    fake_client = FakeClient()

    monkeypatch.setattr(
        module,
        "load_github_connection",
        lambda extra: ("https://api.github.com", "github_pat_123"),
    )
    monkeypatch.setattr(module, "create_github_client", lambda base_url, user_token: fake_client)

    ctx = SimpleNamespace(deps=SimpleNamespace(extra={}))

    result = asyncio.run(module.handler(ctx, repo="cloudchef/atlasclaw", path="pulls/55"))

    assert fake_client.calls == [("/repos/cloudchef/atlasclaw/pulls/55", None)]
    assert result["is_error"] is False
    assert result["details"]["data"]["title"] == "Fix deploy flow"


def test_github_api_query_handler_rejects_non_repo_relative_paths(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "load_github_connection",
        lambda extra: ("https://api.github.com", "github_pat_123"),
    )

    ctx = SimpleNamespace(deps=SimpleNamespace(extra={}))

    result = asyncio.run(module.handler(ctx, repo="cloudchef/atlasclaw", path="/user"))

    assert result["is_error"] is True
    assert "read-only repo-relative path" in result["content"][0]["text"]
