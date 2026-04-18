from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO_ROOT
    / "providers"
    / "github"
    / "skills"
    / "shared"
    / "scripts"
    / "_github_client.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_github_client_module", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_load_github_connection_resolves_default_user_token():
    module = load_module()

    base_url, token = module.load_github_connection(
        {
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

    assert base_url == "https://api.github.com"
    assert token == "github_pat_123"


def test_load_github_connection_rejects_missing_user_token():
    module = load_module()

    with pytest.raises(RuntimeError, match="user_token"):
        module.load_github_connection(
            {
                "provider_instances": {
                    "github": {
                        "default": {
                            "base_url": "https://api.github.com",
                            "auth_type": "user_token",
                        }
                    }
                }
            }
        )


def test_build_github_headers_sets_required_rest_headers():
    module = load_module()

    headers = module.build_github_headers("github_pat_123")

    assert headers == {
        "Authorization": "Bearer github_pat_123",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
