from __future__ import annotations

import asyncio
import importlib.util
import io
import sys
import zipfile
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
    / "github-run-failed-logs"
    / "scripts"
    / "handler.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_github_run_failed_logs_module", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def build_logs_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "Deploy to self-hosted runner/2_Deploy.txt",
            "step: Deploy\nerror: self-hosted runner is offline\n",
        )
        archive.writestr(
            "build-and-push/1_Checkout.txt",
            "checkout ok\n",
        )
    return buffer.getvalue()


class FakeClient:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, params=None, follow_redirects=False):
        self.calls.append((url, params, follow_redirects))
        if url == "/repos/cloudchef/atlasclaw/actions/runs/71210809887/jobs":
            return SimpleNamespace(
                status_code=200,
                text="ok",
                json=lambda: {
                    "jobs": [
                        {
                            "name": "Deploy to self-hosted runner",
                            "conclusion": "failure",
                            "steps": [
                                {"name": "Prepare", "conclusion": "success"},
                                {"name": "Deploy", "conclusion": "failure"},
                            ],
                        }
                    ]
                },
            )
        if url == "/repos/cloudchef/atlasclaw/actions/runs/71210809887/logs":
            return SimpleNamespace(
                status_code=200,
                text="ok",
                content=build_logs_zip(),
            )
        raise AssertionError(f"Unexpected GET: {url} {params} {follow_redirects}")


def test_github_run_failed_logs_handler_returns_failed_job_excerpts(monkeypatch):
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

    assert result["is_error"] is False
    assert result["details"]["failed_logs"][0]["job_name"] == "Deploy to self-hosted runner"
    assert "self-hosted runner is offline" in result["details"]["failed_logs"][0]["excerpt"]

