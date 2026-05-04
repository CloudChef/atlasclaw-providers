# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "datasource"
    / "scripts"
    / "list_resource.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_list_resource_module", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def extract_payload(output: str):
    match = re.search(
        r"##RESOURCE_META_START##\s*(.*?)\s*##RESOURCE_META_END##",
        output,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def make_search_item(resource_id: str, name: str):
    return {
        "id": resource_id,
        "name": name,
        "resourceType": "cloudchef.nodes.Compute",
        "componentType": "resource.software.app.tomcat",
        "osType": "LINUX",
        "osDescription": "Ubuntu 20.04 LTS",
        "isAgentInstalled": True,
        "monitorEnabled": True,
        "status": "started",
    }


def make_resource_item(resource_id: str, name: str):
    return {
        "id": resource_id,
        "name": name,
        "resourceType": "cloudchef.nodes.Compute",
        "componentType": "resource.software.app.tomcat",
        "osType": "LINUX",
        "osDescription": "Ubuntu 20.04 LTS",
        "agentVersion": "1.2.3",
        "status": "started",
        "softwareName": "Tomcat",
        "softwareVersion": "9.0.0.M10",
        "properties": {"hostname": f"{name}.corp", "port": 8080},
        "resourceInfo": {"machine": "svr-01"},
        "customProperties": {"status": "stopped", "publicAccess": "private"},
        "extensibleProperties": {"RuntimeProperties": {"status": "runtime-overwrite", "version": "9.0.0.M10"}},
        "extra": {"monitorEnabled": False},
        "softwares": "Tomcat 9.0.0.M10",
    }


def test_main_fetches_resource_views_with_patch_first(monkeypatch):
    module = load_module()
    calls = []

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_request_json(method, path, *, base_url, headers, payload=None, params=None):
        calls.append((method, path, payload, params))
        if method == "PATCH" and path == "/nodes/res-1/view":
            return make_resource_item("res-1", "db-01")
        if method == "PATCH" and path == "/nodes/res-2/view":
            return make_resource_item("res-2", "db-02")
        raise AssertionError(f"Unexpected call: {method} {path}")

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module, "request_json", fake_request_json)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1", "res-2"])

    output = stdout.getvalue()
    payload = extract_payload(output)

    assert exit_code == 0
    assert "Found 2 resource(s)." in output
    assert len(payload) == 2
    assert payload[0]["resourceId"] == "res-1"
    assert payload[0]["sourceEndpoint"] == "/nodes/res-1/view"
    assert payload[0]["fetchStatus"] == "ok"
    assert payload[0]["data"]["softwares"] == "Tomcat 9.0.0.M10"
    assert payload[0]["resource"] == payload[0]["data"]
    assert payload[0]["details"] == {}
    assert payload[0]["missingEvidence"] == []
    assert payload[0]["fallbackUsed"] is False
    assert payload[0]["normalized"]["type"] == "resource.software.app.tomcat"
    assert payload[0]["normalized"]["properties"]["softwareVersion"] == "9.0.0.M10"
    assert payload[0]["normalized"]["properties"]["status"] == "started"
    assert calls == [
        ("PATCH", "/nodes/res-1/view", None, None),
        ("PATCH", "/nodes/res-2/view", None, None),
    ]


def test_main_uses_legacy_fallback_when_view_fails(monkeypatch):
    module = load_module()

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_request_json(method, path, *, base_url, headers, payload=None, params=None):
        if method == "PATCH" and path == "/nodes/res-1/view":
            return make_resource_item("res-1", "db-01")
        if method == "PATCH" and path == "/nodes/res-2/view":
            raise RuntimeError("HTTP 400: No value present")
        if method == "GET" and path == "/nodes/res-2":
            return make_resource_item("res-2", "db-02")
        if method == "GET" and path == "/nodes/res-2/details":
            return {"runtime": "legacy"}
        raise AssertionError(f"Unexpected call: {method} {path}")

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module, "request_json", fake_request_json)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1", "res-2"])

    output = stdout.getvalue()
    payload = extract_payload(output)

    assert exit_code == 0
    assert len(payload) == 2
    assert payload[1]["resourceId"] == "res-2"
    assert payload[1]["fetchStatus"] == "ok"
    assert payload[1]["data"]["name"] == "db-02"
    assert payload[1]["details"] == {"runtime": "legacy"}
    assert payload[1]["missingEvidence"] == []
    assert payload[1]["fallbackUsed"] is True
    assert payload[1]["errors"] == [
        "Primary PATCH /nodes/res-2/view failed: HTTP 400: No value present"
    ]


def test_main_marks_missing_resource_view_as_error(monkeypatch):
    module = load_module()

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_request_json(method, path, *, base_url, headers, payload=None, params=None):
        if method == "PATCH" and path == "/nodes/res-1/view":
            return make_resource_item("res-1", "db-01")
        if method == "PATCH" and path == "/nodes/res-missing/view":
            raise RuntimeError("HTTP 404: missing")
        if method == "GET" and path == "/nodes/res-missing":
            raise RuntimeError("HTTP 404: missing")
        raise AssertionError(f"Unexpected call: {method} {path}")

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module, "request_json", fake_request_json)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1", "res-missing"])

    output = stdout.getvalue()
    payload = extract_payload(output)

    assert exit_code == 0
    assert len(payload) == 2
    assert payload[1]["resourceId"] == "res-missing"
    assert payload[1]["fetchStatus"] == "error"
    assert payload[1]["missingEvidence"] == ["resource.data"]
    assert payload[1]["fallbackUsed"] is True
    assert payload[1]["errors"] == [
        "Primary PATCH /nodes/res-missing/view failed: HTTP 404: missing",
        "Fallback GET /nodes/res-missing failed: HTTP 404: missing",
    ]


def test_main_prefers_first_value_when_duplicate_properties_exist(monkeypatch):
    module = load_module()

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_request_json(method, path, *, base_url, headers, payload=None, params=None):
        if method == "PATCH" and path == "/nodes/res-1/view":
            return make_resource_item("res-1", "tomcat-01")
        raise AssertionError(f"Unexpected call: {method} {path}")

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module, "request_json", fake_request_json)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1"])

    payload = extract_payload(stdout.getvalue())
    assert exit_code == 0
    assert payload[0]["normalized"]["properties"]["status"] == "started"
    assert payload[0]["normalized"]["properties"]["port"] == 8080


def test_search_resource_summaries_and_collect_ids(monkeypatch):
    module = load_module()

    def fake_request_json(method, path, *, base_url, headers, payload=None, params=None):
        assert method == "POST"
        assert path == "/nodes/search"
        assert params == {"externalIds": "vm-001"}
        assert payload is None
        return {
            "content": [
                {
                    "id": "res-1",
                    "name": "vm-01",
                    "resourceType": "cloudchef.nodes.Compute",
                    "componentType": "resource.iaas.machine.windows_instance.vsphere",
                    "status": "started",
                    "externalId": "vm-001",
                    "nodeInstanceId": "WindowsServer_abc",
                },
                {
                    "id": "res-2",
                    "name": "vm-01-shadow",
                    "resourceType": "cloudchef.nodes.Compute",
                    "componentType": "resource.iaas.machine.windows_instance.vsphere",
                    "status": "started",
                    "externalId": "vm-001-shadow",
                    "nodeInstanceId": "WindowsServer_xyz",
                },
            ]
        }

    summaries = module.search_resource_summaries(
        base_url="https://cmp.example.com/platform-api",
        headers={"CloudChef-Authenticate": "token"},
        request_fn=fake_request_json,
        params={"externalIds": "vm-001"},
    )

    assert len(summaries) == 2
    assert summaries[0]["id"] == "res-1"
    assert summaries[0]["externalId"] == "vm-001"
    assert summaries[0]["nodeInstanceId"] == "WindowsServer_abc"
    assert module.collect_resource_ids_from_summaries(summaries, expected_name="vm-01") == ["res-1"]


def test_collect_resource_ids_from_summaries_rejects_ambiguous_name_without_preferences():
    module = load_module()
    summaries = [
        {
            "id": "res-1",
            "name": "vm-01",
            "externalId": "vm-001",
            "nodeInstanceId": "node-001",
        },
        {
            "id": "res-2",
            "name": "vm-01",
            "externalId": "vm-002",
            "nodeInstanceId": "node-002",
        },
    ]

    assert module.collect_resource_ids_from_summaries(summaries, expected_name="vm-01") == []


def test_collect_resource_ids_from_summaries_prefers_matching_identifiers_for_name_lookup():
    module = load_module()
    summaries = [
        {
            "id": "res-1",
            "name": "vm-01",
            "externalId": "vm-001",
            "nodeInstanceId": "node-001",
        },
        {
            "id": "res-2",
            "name": "vm-01",
            "externalId": "vm-002",
            "nodeInstanceId": "node-002",
        },
    ]

    assert module.collect_resource_ids_from_summaries(
        summaries,
        expected_name="vm-01",
        preferred_external_id="vm-002",
    ) == ["res-2"]
