# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import requests


REPO_ROOT = Path(__file__).resolve().parents[3]
PROVIDER_ROOT = REPO_ROOT / "providers" / "SmartCMP-Provider"
COMMON_PATH = PROVIDER_ROOT / "skills" / "shared" / "scripts" / "_common.py"


def load_common_module():
    spec = importlib.util.spec_from_file_location("test_smartcmp_common_action_module", COMMON_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


class FakeResponse:
    def __init__(self, payload, *, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def run_script(monkeypatch, argv: list[str], *, fake_get):
    script_path = PROVIDER_ROOT / "skills" / "resource" / "scripts" / "list_all_resource.py"
    module_name = "test_list_all_resource_module"

    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=test-token")
    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(sys, "argv", [script_path.name, *argv])

    stdout = io.StringIO()
    stderr = io.StringIO()
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = module.main(argv)
    finally:
        sys.modules.pop(module_name, None)

    return exit_code, stdout.getvalue(), stderr.getvalue()


def extract_meta(stderr: str):
    match = re.search(
        r"##RESOURCE_DIRECTORY_META_START##\s*(.*?)\s*##RESOURCE_DIRECTORY_META_END##",
        stderr,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def localized(default: str, zh_cn: str) -> dict[str, object]:
    return {
        "default": default,
        "translations": {
            "en-US": default,
            "zh-CN": zh_cn,
        },
    }


def test_ui_helpers_build_user_facing_routes_and_resource_actions():
    common = load_common_module()

    assert common.normalize_ui_base_url("https://cmp.example/platform-api") == "https://cmp.example"
    assert common.normalize_ui_base_url("cmp.example/platform-api") == "https://cmp.example"
    assert (
        common.normalize_ui_base_url("https://cmp.example/tenant/platform-api")
        == "https://cmp.example/tenant"
    )
    assert (
        common.build_ui_hash_href("https://cmp.example/platform-api", "#/main/resource")
        == "https://cmp.example/#/main/resource"
    )
    assert (
        common.build_resource_page_href("cmp.example/platform-api", "res 1/2")
        == "https://cmp.example/#/main/virtual-machines/res%201%2F2/details"
    )
    assert common.build_resource_page_href("cmp.example/platform-api", "") == ""
    assert (
        common.build_resource_page_href(
            "https://cmp.example/platform-api",
            "res-1",
            category="cloud-resource",
        )
        == "https://cmp.example/#/main/cloud-resource/res-1/details"
    )
    assert common.build_resource_object_actions("cmp.example/platform-api", "res-1") == [
        {
            "action_id": "open_detail",
            "kind": "open_url",
            "display_label": localized("Open", "打开"),
            "href": "https://cmp.example/#/main/virtual-machines/res-1/details",
            "effect": "navigate",
            "tone": "default",
        }
    ]
    assert common.build_resource_object_actions(
        "cmp.example/platform-api",
        "res-1",
        resource_name="资源A",
        include_detail_action=True,
    ) == [
        {
            "action_id": "view_detail",
            "kind": "agent_prompt",
            "display_label": localized("View details", "查看详情"),
            "effect": "read",
            "tone": "default",
            "agent_prompt": localized("Show resource details for res-1", "查看 res-1 的资源详情"),
        },
        {
            "action_id": "open_detail",
            "kind": "open_url",
            "display_label": localized("Open", "打开"),
            "href": "https://cmp.example/#/main/virtual-machines/res-1/details",
            "effect": "navigate",
            "tone": "default",
        },
    ]


def test_list_all_resource_hits_all_resources_api_and_emits_object_actions(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, verify=None, timeout=None):
        captured["url"] = url
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "res-1",
                        "name": "资源A",
                        "resourceType": "cloudchef.nodes.Compute",
                        "componentType": "iaas.machine.virtual_machine",
                        "status": "started",
                    }
                ]
            }
        )

    exit_code, stdout, stderr = run_script(monkeypatch, [], fake_get=fake_get)
    payload = extract_meta(stderr)

    assert exit_code == 0
    assert captured["url"] == (
        "https://cmp.example.com/platform-api/nodes/search"
        "?page=1&size=20&queryValue=&sort=createdDate%2Cdesc&relation=AND&fullMatch=false&category=-1"
    )
    assert "Found 1 resource(s):" in stdout
    assert "| # | Name | Status | Resource Type | Component Type |" in stdout
    assert "| --- | --- | --- | --- | --- |" in stdout
    assert "| 1 | 资源A | started | cloudchef.nodes.Compute | iaas.machine.virtual_machine |" in stdout
    assert payload[0]["scope"] == "all_resources"
    assert payload[0]["id"] == "res-1"
    assert payload[0]["object_type"] == "cloud_resource"
    assert payload[0]["object_id"] == "res-1"
    assert payload[0]["object_name"] == "资源A"
    assert payload[0]["object_actions"] == [
        {
            "action_id": "view_detail",
            "kind": "agent_prompt",
            "display_label": localized("View details", "查看详情"),
            "effect": "read",
            "tone": "default",
            "agent_prompt": localized("Show resource details for res-1", "查看 res-1 的资源详情"),
        },
        {
            "action_id": "open_detail",
            "kind": "open_url",
            "display_label": localized("Open", "打开"),
            "href": "https://cmp.example.com/#/main/cloud-resource/res-1/details",
            "effect": "navigate",
            "tone": "default",
        }
    ]
    assert "https://cmp.example.com/#/main/cloud-resource/res-1/details" not in stdout


def test_list_all_resource_hits_virtual_machine_ui_url(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, verify=None, timeout=None):
        captured["url"] = url
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "vm-1",
                        "name": "云主机A",
                        "resourceType": "cloudchef.nodes.Compute",
                        "componentType": "iaas.machine.virtual_machine",
                        "status": "running",
                        "os": "Linux",
                    }
                ]
            }
        )

    exit_code, stdout, stderr = run_script(
        monkeypatch,
        ["--scope", "virtual_machines", "--query-value", "生产"],
        fake_get=fake_get,
    )
    payload = extract_meta(stderr)

    assert exit_code == 0
    assert captured["url"] == (
        "https://cmp.example.com/platform-api/nodes/search"
        "?query&page=1&size=20&catalogGroupIds=&sort=createdDate%2Cdesc"
        "&queryValue=%E7%94%9F%E4%BA%A7&category=iaas.machine.virtual_machine"
        "&componentType=&monitorEnabled=&cloudEntryType=&isAgentInstalled=&os="
        "&groupIds=&isImported=&relation=AND&fullMatch=false"
    )
    assert "Found 1 virtual machine(s):" in stdout
    assert "| # | Name | Status | OS |" in stdout
    assert "| --- | --- | --- | --- |" in stdout
    assert "| 1 | 云主机A | running | Linux |" in stdout
    assert payload[0]["scope"] == "virtual_machines"
    assert payload[0]["os"] == "Linux"
    assert payload[0]["object_type"] == "virtual_machine"
    assert payload[0]["object_id"] == "vm-1"
    assert payload[0]["object_name"] == "云主机A"
    assert payload[0]["object_actions"][0]["display_label"] == localized("View details", "查看详情")
    assert payload[0]["object_actions"][0]["agent_prompt"] == localized(
        "Show resource details for vm-1",
        "查看 vm-1 的资源详情",
    )
    assert payload[0]["object_actions"][1]["href"] == (
        "https://cmp.example.com/#/main/virtual-machines/vm-1/details"
    )
    assert payload[0]["object_actions"][1]["display_label"] == localized("Open", "打开")
    assert "https://cmp.example.com/#/main/virtual-machines/vm-1/details" not in stdout


def test_list_all_resource_escapes_markdown_table_cells(monkeypatch):
    def fake_get(url, headers=None, verify=None, timeout=None):
        return FakeResponse(
            {
                "content": [
                    {
                        "id": "vm-escape",
                        "name": "prod|db\nprimary",
                        "resourceType": "cloudchef.nodes.Compute",
                        "componentType": "iaas.machine.virtual_machine",
                        "status": "started|healthy",
                        "os": "Linux\nCentOS",
                    }
                ]
            }
        )

    exit_code, stdout, _stderr = run_script(
        monkeypatch,
        ["--scope", "virtual_machines"],
        fake_get=fake_get,
    )

    assert exit_code == 0
    assert "| 1 | prod\\|db primary | started\\|healthy | Linux CentOS |" in stdout
