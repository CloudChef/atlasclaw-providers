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
SCRIPT_PATH = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "resource"
    / "scripts"
    / "resource_detail.py"
)


class FakeResponse:
    def __init__(self, payload, *, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def load_module():
    spec = importlib.util.spec_from_file_location("test_resource_detail_analysis_module", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def extract_meta(stderr: str):
    match = re.search(
        r"##RESOURCE_DETAIL_META_START##\s*(.*?)\s*##RESOURCE_DETAIL_META_END##",
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


def test_main_renders_compact_resource_detail(monkeypatch):
    module = load_module()
    captured = {}

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_get(url, headers=None, verify=None, timeout=None):
        captured["url"] = url
        return FakeResponse(
            {
                "id": "res-1",
                "name": "mysqlLinux2",
                "status": "started",
                "hostName": "Compute-9fxzdy",
                "osDescription": "CentOS",
                "imageName": "CentOS 4/5 or newer (64-bit)",
                "sshPort": 22,
                "lastStartedDate": "2026-04-18 23:39:30",
                "externalId": "vm-403",
                "cpus": 1,
                "memory": 1024,
                "diskTotalNum": 1,
                "storage": 50,
                "host": "host-75",
                "deploymentName": "mysqlLinux2",
                "createdDate": "2026-04-18 23:42:05",
                "payType": "PayAsYouGo",
                "leaseType": "Never",
                "retentionAt": "Never",
                "businessGroupName": "team1",
                "ownerName": "platform-admin",
                "cloudEntryType": "vSphere",
                "cloudEntryName": "vsphere",
                "resourceBundleName": "vsphere-pool",
                "vcenterServer": "192.168.1.113",
                "vcenterFolder": "Datacenter1",
                "storagePolicy": "default-storage-policy",
                "ipAddress": "192.168.92.104",
                "physicalHost": "192.168.1.170",
                "physicalManufacturer": "Dell Inc.",
                "physicalModel": "PowerEdge R720",
                "physicalCpuType": "Intel Xeon",
                "physicalCpuUsage": "21.54%",
                "physicalMemoryUsage": "94.39%",
            }
        )

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(requests, "patch", fake_get)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["res-1"])

    output = stdout.getvalue()
    meta = extract_meta(stderr.getvalue())

    assert exit_code == 0
    assert captured["url"] == "https://cmp.example.com/platform-api/nodes/res-1/view"
    assert meta["object_type"] == "virtual_machine"
    assert meta["object_id"] == "res-1"
    assert meta["object_name"] == "mysqlLinux2"
    assert meta["object_actions"] == [
        {
            "action_id": "open_detail",
            "kind": "open_url",
            "display_label": localized("Open", "打开"),
            "href": "https://cmp.example.com/#/main/virtual-machines/res-1/details",
            "effect": "navigate",
            "tone": "default",
        },
        {
            "action_id": "analyze",
            "kind": "agent_prompt",
            "display_label": localized("Analyze", "分析"),
            "agent_prompt": localized("Analyze resource res-1", "分析资源 res-1"),
            "effect": "read",
            "tone": "default",
        },
        {
            "action_id": "list_operations",
            "kind": "agent_prompt",
            "display_label": localized("Operations", "操作"),
            "agent_prompt": localized(
                    "List available operations for resource res-1",
                    "查看资源 res-1 的可用操作",
            ),
            "effect": "read",
            "tone": "default",
        }
    ]
    assert "https://cmp.example.com/#/main/virtual-machines/res-1/details" not in output
    assert "mysqlLinux2" in output
    assert "- Status: started" in output
    assert "- Compute: 1 CPU / 1 GB" in output
    assert "Basic Information" in output
    assert "- Operating System: CentOS" in output
    assert "Attributes" in output
    assert "- Cloud Resource ID: vm-403" in output
    assert "Service Information" in output
    assert "Organization Information" in output
    assert "Platform Information" in output
    assert "Disks" in output
    assert "- Disk 1: 50 | CentOS 4/5 or newer (64-bit)" in output
    assert "topLevelKeys" not in output
    assert "sourceEndpoint" not in output


def test_main_resolves_unique_resource_name_before_detail(monkeypatch):
    module = load_module()
    captured = {"search_url": "", "detail_url": ""}

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_search(url, headers=None, verify=None, timeout=None):
        captured["search_url"] = url
        return FakeResponse(
            {
                "content": [
                    {"id": "res-other", "name": "mysqlLinux20", "status": "started"},
                    {"id": "res-1", "name": "mysqlLinux2", "status": "started"},
                ]
            }
        )

    def fake_detail(url, headers=None, verify=None, timeout=None):
        captured["detail_url"] = url
        return FakeResponse(
            {
                "id": "res-1",
                "name": "mysqlLinux2",
                "status": "started",
                "cpus": 2,
                "memory": 2048,
                "ipAddress": "192.168.24.109",
            }
        )

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module.requests, "get", fake_search)
    monkeypatch.setattr(module.requests, "patch", fake_detail)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["--resource-name", "mysqlLinux2"])

    output = stdout.getvalue()
    meta = extract_meta(stderr.getvalue())

    assert exit_code == 0
    assert captured["search_url"] == (
        "https://cmp.example.com/platform-api/nodes/search"
        "?query&page=1&size=100&catalogGroupIds=&sort=createdDate%2Cdesc"
        "&queryValue=mysqlLinux2&category=iaas.machine.virtual_machine"
        "&componentType=&monitorEnabled=&cloudEntryType=&isAgentInstalled=&os="
        "&groupIds=&isImported=&relation=AND&fullMatch=true"
    )
    assert captured["detail_url"] == "https://cmp.example.com/platform-api/nodes/res-1/view"
    assert meta["resourceId"] == "res-1"
    assert meta["object_actions"][0]["href"] == (
        "https://cmp.example.com/#/main/virtual-machines/res-1/details"
    )
    assert meta["object_actions"][0]["display_label"] == localized("Open", "打开")
    assert "Found 2 virtual machine(s)" not in output
    assert "mysqlLinux20" not in output
    assert "mysqlLinux2" in output
    assert "- Compute: 2 CPU / 2 GB" in output


def test_main_resolves_resource_name_from_nested_search_payload(monkeypatch):
    module = load_module()
    captured = {"detail_url": ""}

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_search(url, headers=None, verify=None, timeout=None):
        return FakeResponse(
            {
                "data": {
                    "content": [
                        {"id": "res-1", "name": "mysqlLinux2", "status": "started"},
                    ],
                    "totalElements": 1,
                }
            }
        )

    def fake_detail(url, headers=None, verify=None, timeout=None):
        captured["detail_url"] = url
        return FakeResponse({"id": "res-1", "name": "mysqlLinux2", "status": "started"})

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module.requests, "get", fake_search)
    monkeypatch.setattr(module.requests, "patch", fake_detail)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["--resource-name", "mysqlLinux2"])

    assert exit_code == 0
    assert captured["detail_url"] == "https://cmp.example.com/platform-api/nodes/res-1/view"
    assert extract_meta(stderr.getvalue())["resourceId"] == "res-1"
    assert "mysqlLinux2" in stdout.getvalue()


def test_main_checks_later_pages_before_accepting_unique_resource_name(monkeypatch):
    module = load_module()
    requested_urls = []
    patch_called = False

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_search(url, headers=None, verify=None, timeout=None):
        requested_urls.append(url)
        if "page=1" in url:
            return FakeResponse(
                {
                    "content": [
                        {"id": "res-1", "name": "mysqlLinux2", "status": "started"},
                    ],
                    "totalElements": 2,
                }
            )
        return FakeResponse(
            {
                "content": [
                    {"id": "res-2", "name": "mysqlLinux2", "status": "stopped"},
                ],
                "totalElements": 2,
            }
        )

    def fake_detail(url, headers=None, verify=None, timeout=None):
        nonlocal patch_called
        patch_called = True
        return FakeResponse({})

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module.requests, "get", fake_search)
    monkeypatch.setattr(module.requests, "patch", fake_detail)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["--resource-name", "mysqlLinux2"])

    output = stdout.getvalue()
    assert exit_code == 1
    assert len(requested_urls) == 2
    assert "page=1" in requested_urls[0]
    assert "page=2" in requested_urls[1]
    assert not patch_called
    assert stderr.getvalue() == ""
    assert "Multiple virtual machines exactly matched name 'mysqlLinux2'" in output


def test_main_requires_unique_resource_name(monkeypatch):
    module = load_module()
    patch_called = False

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_search(url, headers=None, verify=None, timeout=None):
        return FakeResponse(
            {
                "content": [
                    {"id": "res-1", "name": "mysqlLinux2", "status": "started"},
                    {"id": "res-2", "name": "mysqlLinux2", "status": "stopped"},
                ]
            }
        )

    def fake_detail(url, headers=None, verify=None, timeout=None):
        nonlocal patch_called
        patch_called = True
        return FakeResponse({})

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module.requests, "get", fake_search)
    monkeypatch.setattr(module.requests, "patch", fake_detail)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["--resource-name", "mysqlLinux2"])

    output = stdout.getvalue()
    assert exit_code == 1
    assert not patch_called
    assert stderr.getvalue() == ""
    assert "Multiple virtual machines exactly matched name 'mysqlLinux2'" in output
    assert "| # | Name | Status |" in output
    assert "| 1 | mysqlLinux2 | started |" in output
    assert "| 2 | mysqlLinux2 | stopped |" in output
    assert "res-1" not in output
    assert "res-2" not in output


def test_main_prints_response_body_for_request_errors(monkeypatch):
    module = load_module()

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_get(url, headers=None, verify=None, timeout=None):
        raise requests.HTTPError(
            "HTTP 400",
            response=FakeResponse({}, status_code=400, text='{"message":"bad request"}'),
        )

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(requests, "patch", fake_get)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-2"])

    output = stdout.getvalue()
    assert exit_code == 1
    assert "Request failed" in output
    assert '{"message":"bad request"}' in output
