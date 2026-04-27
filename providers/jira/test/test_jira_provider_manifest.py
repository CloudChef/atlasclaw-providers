# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import json
from pathlib import Path

PROVIDER_ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict:
    return json.loads((PROVIDER_ROOT / "provider.schema.json").read_text(encoding="utf-8"))


def test_jira_provider_manifest_declares_runtime_catalog_metadata() -> None:
    manifest = _manifest()

    assert manifest["schema_version"] == 1
    assert manifest["provider_type"] == "jira"
    assert manifest["catalog"]["display_name"] == "Jira"
    assert manifest["catalog"]["icon_path"] == "assets/icon.svg"
    assert (PROVIDER_ROOT / manifest["catalog"]["icon_path"]).is_file()


def test_jira_provider_manifest_uses_password_as_canonical_credential_secret() -> None:
    manifest = _manifest()
    config_schema = manifest["config_schema"]
    fields = {field["name"]: field for field in config_schema["fields"]}

    assert config_schema["default_auth_type"] == "credential"
    assert config_schema["auth_modes"]["credential"]["required_fields"] == [
        "username",
        "password",
    ]
    assert "token" not in fields
    assert fields["password"]["label"] == "Password / API Token"
    assert fields["password"]["sensitive"] is True
    assert "aliases" not in fields["password"]
