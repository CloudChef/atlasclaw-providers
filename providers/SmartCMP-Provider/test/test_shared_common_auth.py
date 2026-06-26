# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "shared"
    / "scripts"
    / "_common.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_shared_common_module", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_infer_auth_url_uses_private_login_for_private_cloud_subdomain():
    module = load_module()

    auth_url = module._infer_auth_url("https://democmp.smartcmp.cloud:1443/platform-api")

    assert auth_url == "https://democmp.smartcmp.cloud:1443/platform-api/login"


def test_infer_auth_url_keeps_known_saas_console_mapping():
    module = load_module()

    auth_url = module._infer_auth_url("https://console.smartcmp.cloud")

    assert auth_url == module._SAAS_AUTH_URL


def test_resolve_auth_url_prefers_explicit_override():
    module = load_module()

    auth_url = module._resolve_auth_url(
        "https://console.smartcmp.cloud",
        "https://democmp.smartcmp.cloud:1443/platform-api/login",
    )

    assert auth_url == "https://democmp.smartcmp.cloud:1443/platform-api/login"


def test_request_timeout_defaults_to_sixty_seconds(monkeypatch):
    monkeypatch.delenv("CMP_TIMEOUT", raising=False)
    module = load_module()

    assert module.request_timeout() == 60
    assert module.get_request_timeout({}) == 60


def test_request_timeout_prefers_provider_config_over_environment(monkeypatch):
    monkeypatch.setenv("CMP_TIMEOUT", "45")
    module = load_module()

    assert module.get_request_timeout({"timeout": "75"}) == 75


def test_request_timeout_ignores_environment_when_provider_config_has_no_timeout(monkeypatch):
    monkeypatch.setenv("CMP_TIMEOUT", "45")
    monkeypatch.setenv("ATLASCLAW_COOKIES", "{}")
    monkeypatch.setenv(
        "ATLASCLAW_PROVIDER_CONFIG",
        json.dumps(
            {
                "smartcmp": {
                    "prod": {
                        "base_url": "https://cmp.example.com",
                        "provider_token": "provider-token",
                    }
                }
            }
        ),
    )
    monkeypatch.delenv("CMP_URL", raising=False)
    module = load_module()

    assert module.request_timeout() == 60


def test_request_timeout_accepts_environment_for_local_script_execution(monkeypatch):
    monkeypatch.setenv("CMP_TIMEOUT", "45")
    module = load_module()

    assert module.request_timeout() == 45
    assert module.get_request_timeout({}) == 45


def test_request_timeout_uses_default_for_invalid_or_non_positive_values(monkeypatch):
    monkeypatch.setenv("CMP_TIMEOUT", "invalid")
    module = load_module()

    assert module.request_timeout() == 60
    assert module.get_request_timeout({"timeout": "0"}) == 60
    assert module.get_request_timeout({"timeout": "-1"}) == 60
