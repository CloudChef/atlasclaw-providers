# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
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
