# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import json
import re
from pathlib import Path

PROVIDER_ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict:
    return json.loads((PROVIDER_ROOT / "provider.schema.json").read_text(encoding="utf-8"))


def test_smartcmp_provider_manifest_declares_runtime_catalog_metadata() -> None:
    manifest = _manifest()

    assert manifest["schema_version"] == 1
    assert manifest["provider_type"] == "smartcmp"
    assert manifest["catalog"]["display_name"] == "SmartCMP"
    assert manifest["catalog"]["icon_path"] == "assets/icon.svg"
    assert (PROVIDER_ROOT / manifest["catalog"]["icon_path"]).is_file()


def test_smartcmp_provider_manifest_declares_auth_modes_and_sensitive_fields() -> None:
    manifest = _manifest()
    config_schema = manifest["config_schema"]
    fields = {field["name"]: field for field in config_schema["fields"]}

    assert config_schema["default_auth_type"] == "user_token"
    assert config_schema["auth_modes"] == {
        "provider_token": {"required_fields": ["provider_token"]},
        "user_token": {"required_fields": ["user_token"]},
        "cookie": {"required_fields": ["cookie"]},
        "credential": {"required_fields": ["username", "password"]},
    }
    assert "default_business_group" not in fields

    sensitive_fields = {
        name
        for name, field in fields.items()
        if field.get("sensitive") is True or field.get("type") == "password"
    }
    assert {"user_token", "provider_token", "password", "cookie"}.issubset(sensitive_fields)


def test_changed_workflow_mutations_declare_mutation_group() -> None:
    mutating_tool_groups = {
        "preapproval-agent/SKILL.md": ("tool_approve", "tool_reject"),
        "request/SKILL.md": ("tool_submit",),
    }

    for relative_path, tool_prefixes in mutating_tool_groups.items():
        skill_text = (
            PROVIDER_ROOT / "skills" / relative_path
        ).read_text(encoding="utf-8")
        for tool_prefix in tool_prefixes:
            match = re.search(
                rf"^{tool_prefix}_groups:\n(?P<groups>(?:  - .+\n)+)",
                skill_text,
                flags=re.MULTILINE,
            )
            assert match is not None, f"{relative_path}: missing {tool_prefix}_groups"
            assert "  - mutation\n" in match.group("groups"), (
                f"{relative_path}: {tool_prefix} must declare mutation"
            )
