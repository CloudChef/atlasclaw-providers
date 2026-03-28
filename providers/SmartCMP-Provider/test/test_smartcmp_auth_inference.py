from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "shared" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _common as common  # noqa: E402


def _fake_auto_login(calls):
    def _login(auth_url: str, username: str, password: str) -> str:
        calls.append({
            "auth_url": auth_url,
            "username": username,
            "password": password,
        })
        return "CloudChef-Authenticate=test-token; session=abc"

    return _login


def test_infer_auth_url_for_console_saas_host():
    assert (
        common._infer_auth_url("https://console.smartcmp.cloud/")
        == "https://account.smartcmp.cloud/bss-api/api/authentication"
    )


def test_infer_auth_url_for_account_saas_host():
    assert (
        common._infer_auth_url("https://account.smartcmp.cloud/#/login")
        == "https://account.smartcmp.cloud/bss-api/api/authentication"
    )


def test_infer_auth_url_for_private_deployment_host():
    assert (
        common._infer_auth_url("https://democmp.smartcmp.cloud:1443")
        == "https://democmp.smartcmp.cloud:1443/platform-api/login"
    )


def test_env_auth_url_override_takes_priority(monkeypatch):
    calls = []
    monkeypatch.setattr(common, "_auto_login", _fake_auto_login(calls))
    monkeypatch.setattr(common, "_get_cached_cookie", lambda *_args, **_kwargs: "")
    monkeypatch.setenv("CMP_URL", "https://democmp.smartcmp.cloud:1443")
    monkeypatch.setenv("CMP_AUTH_URL", "https://login.internal.example/platform-api/login")
    monkeypatch.setenv("CMP_USERNAME", "admin")
    monkeypatch.setenv("CMP_PASSWORD", "secret")
    monkeypatch.delenv("CMP_COOKIE", raising=False)

    base_url, auth_token, instance = common._get_config_from_env()

    assert calls == [
        {
            "auth_url": "https://login.internal.example/platform-api/login",
            "username": "admin",
            "password": "secret",
        }
    ]
    assert base_url == "https://democmp.smartcmp.cloud:1443/platform-api"
    assert auth_token == "test-token"
    assert instance["base_url"] == "https://democmp.smartcmp.cloud:1443"


def test_skilldeps_auth_url_override_takes_priority(monkeypatch):
    calls = []
    monkeypatch.setattr(common, "_auto_login", _fake_auto_login(calls))
    monkeypatch.setattr(common, "_get_cached_cookie", lambda *_args, **_kwargs: "")
    monkeypatch.setenv("ATLASCLAW_COOKIES", "{}")
    monkeypatch.setenv(
        "ATLASCLAW_PROVIDER_CONFIG",
        json.dumps(
            {
                "smartcmp": {
                    "prod": {
                        "base_url": "https://democmp.smartcmp.cloud:1443",
                        "auth_url": "https://login.internal.example/platform-api/login",
                        "username": "admin",
                        "password": "secret",
                    }
                }
            }
        ),
    )

    base_url, auth_token, instance = common._get_config_from_skilldeps()

    assert calls == [
        {
            "auth_url": "https://login.internal.example/platform-api/login",
            "username": "admin",
            "password": "secret",
        }
    ]
    assert base_url == "https://democmp.smartcmp.cloud:1443/platform-api"
    assert auth_token == "test-token"
    assert instance["auth_url"] == "https://login.internal.example/platform-api/login"
