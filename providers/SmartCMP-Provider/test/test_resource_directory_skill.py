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


def test_list_all_resource_hits_all_resources_ui_url(monkeypatch):
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
    assert "资源A | status: started" in stdout
    assert payload[0]["scope"] == "all_resources"
    assert payload[0]["id"] == "res-1"


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
    assert "云主机A | status: running" in stdout
    assert payload[0]["scope"] == "virtual_machines"
    assert payload[0]["os"] == "Linux"
