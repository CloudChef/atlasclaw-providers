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
    / "github-run-view"
    / "scripts"
    / "handler.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_github_run_view_module", MODULE_PATH)
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
        if url == "/repos/cloudchef/atlasclaw/actions/runs/71210809887":
            return SimpleNamespace(
                status_code=200,
                text="ok",
                json=lambda: {
                    "id": 71210809887,
                    "name": "build.yml",
                    "status": "completed",
                    "conclusion": "failure",
                    "head_branch": "main",
                    "html_url": "https://github.com/run/71210809887",
                },
            )
        if url == "/repos/cloudchef/atlasclaw/actions/runs/71210809887/jobs":
            return SimpleNamespace(
                status_code=200,
                text="ok",
                json=lambda: {
                    "jobs": [
                        {
                            "name": "build-and-push",
                            "conclusion": "success",
                            "steps": [
                                {"name": "Checkout", "conclusion": "success"},
                            ],
                        },
                        {
                            "name": "Deploy to self-hosted runner",
                            "conclusion": "failure",
                            "steps": [
                                {"name": "Prepare", "conclusion": "success"},
                                {"name": "Deploy", "conclusion": "failure"},
                            ],
                        },
                    ]
                },
            )
        raise AssertionError(f"Unexpected GET: {url} {params}")


def test_github_run_view_handler_returns_run_and_failed_steps(monkeypatch):
    module = load_module()
    fake_client = FakeClient()

    monkeypatch.setattr(
        module,
        "load_github_connection",
        lambda extra: ("https://api.github.com", "github_pat_123"),
    )
    monkeypatch.setattr(module, "create_github_client", lambda base_url, user_token: fake_client)

    ctx = SimpleNamespace(deps=SimpleNamespace(extra={}))

    result = asyncio.run(module.handler(ctx, repo="cloudchef/atlasclaw", run_id=71210809887))

    assert fake_client.calls == [
        ("/repos/cloudchef/atlasclaw/actions/runs/71210809887", None),
        ("/repos/cloudchef/atlasclaw/actions/runs/71210809887/jobs", {"per_page": 100, "page": 1}),
    ]
    assert result["is_error"] is False
    assert result["details"]["run"]["run_id"] == 71210809887
    assert result["details"]["jobs"][1]["failed_steps"] == ["Deploy"]

