from __future__ import annotations

import json
from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]


def test_weaver_provider_package_layout() -> None:
    assert (PROVIDER_ROOT / "PROVIDER.md").is_file()
    assert (PROVIDER_ROOT / "README.md").is_file()
    assert (PROVIDER_ROOT / "provider.schema.json").is_file()
    assert (PROVIDER_ROOT / "assets" / "icon.svg").is_file()


def test_weaver_provider_manifest_declares_sso_schema() -> None:
    manifest = json.loads((PROVIDER_ROOT / "provider.schema.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["provider_type"] == "weaver_ecology"
    assert manifest["catalog"]["icon_path"] == "assets/icon.svg"
    assert manifest["config_schema"]["default_auth_type"] == "sso"
    assert manifest["config_schema"]["auth_modes"]["sso"]["required_fields"] == []

    fields = {
        field["name"]: field
        for field in manifest["config_schema"]["fields"]
    }
    assert fields["base_url"]["required"] is True
    assert fields["auth_type"]["default"] == "sso"
    assert fields["sso_token_mode"]["default"] == "access_token"
    assert fields["oauth_app_secret"]["sensitive"] is True
    assert "oauth_app_secret" in manifest["redaction"]["sensitive_fields"]
