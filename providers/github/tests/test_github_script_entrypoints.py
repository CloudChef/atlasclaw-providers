from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_SCRIPTS = [
    REPO_ROOT / "providers" / "github" / "skills" / "github-repo" / "scripts" / "handler.py",
    REPO_ROOT / "providers" / "github" / "skills" / "github-pr-checks" / "scripts" / "handler.py",
    REPO_ROOT / "providers" / "github" / "skills" / "github-run-list" / "scripts" / "handler.py",
    REPO_ROOT / "providers" / "github" / "skills" / "github-run-view" / "scripts" / "handler.py",
    REPO_ROOT
    / "providers"
    / "github"
    / "skills"
    / "github-run-failed-logs"
    / "scripts"
    / "handler.py",
    REPO_ROOT / "providers" / "github" / "skills" / "github-api-query" / "scripts" / "handler.py",
]


@pytest.mark.parametrize("script_path", SKILL_SCRIPTS)
def test_github_script_entrypoints_do_not_depend_on_atlasclaw_imports(script_path: Path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["USER_TOKEN"] = ""
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(script_path.parent),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    combined_output = f"{result.stdout}\n{result.stderr}"

    assert result.returncode != 0
    assert "No module named 'app'" not in combined_output
    assert "GitHub provider config missing required field: user_token" in combined_output
