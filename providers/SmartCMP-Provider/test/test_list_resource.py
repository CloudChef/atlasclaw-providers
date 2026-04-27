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


def test_main_merges_search_resource_and_detail_calls(monkeypatch):
    module = load_module()
    calls = []

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_request_json(method, path, *, base_url, headers, payload=None, params=None):
        calls.append((method, path, payload, params))
        if method == "POST" and path == "/nodes/search":
            assert payload == {"ids": ["res-1", "res-2"]}
            return {"content": [make_search_item("res-1", "db-01"), make_search_item("res-2", "db-02")]}
        if method == "GET" and path == "/nodes/res-1":
            return make_resource_item("res-1", "db-01")
        if method == "GET" and path == "/nodes/res-1/details":
            return {"osVersion": "Ubuntu 20.04", "kernel": "5.15.0"}
        if method == "GET" and path == "/nodes/res-2":
            return make_resource_item("res-2", "db-02")
        if method == "GET" and path == "/nodes/res-2/details":
            return {"osVersion": "Ubuntu 20.04", "kernel": "5.15.1"}
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
    assert payload[0]["fetchStatus"] == "ok"
    assert payload[0]["details"]["osVersion"] == "Ubuntu 20.04"
    assert payload[0]["resource"]["softwares"] == "Tomcat 9.0.0.M10"
    assert payload[0]["normalized"]["type"] == "resource.software.app.tomcat"
    assert payload[0]["normalized"]["properties"]["softwareVersion"] == "9.0.0.M10"
    assert payload[0]["normalized"]["properties"]["status"] == "started"
    assert calls[0][1] == "/nodes/search"


def test_main_marks_partial_failure_for_one_resource(monkeypatch):
    module = load_module()

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_request_json(method, path, *, base_url, headers, payload=None, params=None):
        if method == "POST" and path == "/nodes/search":
            return {"content": [make_search_item("res-1", "db-01"), make_search_item("res-2", "db-02")]}
        if method == "GET" and path == "/nodes/res-1":
            return make_resource_item("res-1", "db-01")
        if method == "GET" and path == "/nodes/res-1/details":
            return {"osVersion": "Ubuntu 20.04"}
        if method == "GET" and path == "/nodes/res-2":
            return make_resource_item("res-2", "db-02")
        if method == "GET" and path == "/nodes/res-2/details":
            raise RuntimeError("details unavailable")
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
    assert payload[1]["fetchStatus"] == "partial"
    assert payload[1]["details"] == {}
    assert payload[1]["errors"] == ["details unavailable"]


def test_main_marks_missing_resource_as_not_found(monkeypatch):
    module = load_module()

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_request_json(method, path, *, base_url, headers, payload=None, params=None):
        if method == "POST" and path == "/nodes/search":
            return {"content": [make_search_item("res-1", "db-01")]}
        if method == "GET" and path == "/nodes/res-1":
            return make_resource_item("res-1", "db-01")
        if method == "GET" and path == "/nodes/res-1/details":
            return {"osVersion": "Ubuntu 20.04"}
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
    assert payload[1]["fetchStatus"] == "not_found"
    assert payload[1]["errors"] == ["Resource was not returned by /nodes/search."]


def test_main_prefers_first_value_when_duplicate_properties_exist(monkeypatch):
    module = load_module()

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_request_json(method, path, *, base_url, headers, payload=None, params=None):
        if method == "POST" and path == "/nodes/search":
            return {"content": [make_search_item("res-1", "tomcat-01")]}
        if method == "GET" and path == "/nodes/res-1":
            return make_resource_item("res-1", "tomcat-01")
        if method == "GET" and path == "/nodes/res-1/details":
            return {"status": "from-details", "port": 9090}
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
