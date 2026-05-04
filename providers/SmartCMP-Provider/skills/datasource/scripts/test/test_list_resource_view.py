# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Tests for SmartCMP resource evidence loading."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "list_resource.py"
SPEC = importlib.util.spec_from_file_location("smartcmp_list_resource", SCRIPT_PATH)
list_resource = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(list_resource)


def test_load_resource_records_uses_patch_view_endpoint_first():
    calls = []
    view_payload = {
        "id": "res-1",
        "name": "vm-1",
        "componentType": "resource.iaas.machine.instance.vsphere",
        "status": "started",
        "properties": {"cpu": 2, "memoryInGB": 4},
    }

    def request_fn(method, path, *, base_url, headers, payload=None, params=None):
        calls.append((method, path, payload, params))
        assert method == "PATCH"
        assert path == "/nodes/res-1/view"
        return view_payload

    records = list_resource.load_resource_records(
        ["res-1"],
        base_url="https://cmp.example/platform-api",
        headers={},
        request_fn=request_fn,
    )

    assert calls == [("PATCH", "/nodes/res-1/view", None, None)]
    assert records[0]["resourceId"] == "res-1"
    assert records[0]["sourceEndpoint"] == "/nodes/res-1/view"
    assert records[0]["fetchStatus"] == "ok"
    assert records[0]["data"] == view_payload
    assert records[0]["resource"] == view_payload
    assert records[0]["missingEvidence"] == []
    assert records[0]["errors"] == []
    assert records[0]["normalized"]["type"] == "resource.iaas.machine.instance.vsphere"
    assert records[0]["normalized"]["properties"]["cpu"] == 2


def test_view_failure_uses_legacy_resource_fallback():
    calls = []

    def request_fn(method, path, *, base_url, headers, payload=None, params=None):
        calls.append((method, path, payload, params))
        if method == "PATCH" and path == "/nodes/res-1/view":
            raise RuntimeError("HTTP 400: No value present")
        if method == "GET" and path == "/nodes/res-1":
            return {
                "id": "res-1",
                "name": "vm-1",
                "componentType": "resource.iaas.machine.instance.vsphere",
                "properties": {"cpu": 2},
            }
        if method == "GET" and path == "/nodes/res-1/details":
            return {"detailsReady": True}
        raise AssertionError(f"Unexpected call: {method} {path}")

    records = list_resource.load_resource_records(
        ["res-1"],
        base_url="https://cmp.example/platform-api",
        headers={},
        request_fn=request_fn,
    )

    assert calls == [
        ("PATCH", "/nodes/res-1/view", None, None),
        ("GET", "/nodes/res-1", None, None),
        ("GET", "/nodes/res-1/details", None, None),
    ]
    assert records[0]["fetchStatus"] == "ok"
    assert records[0]["data"]["name"] == "vm-1"
    assert records[0]["details"] == {"detailsReady": True}
    assert records[0]["missingEvidence"] == []
    assert records[0]["fallbackUsed"] is True
    assert records[0]["fallbackEndpoints"] == ["/nodes/res-1", "/nodes/res-1/details"]
    assert records[0]["errors"] == [
        "Primary PATCH /nodes/res-1/view failed: HTTP 400: No value present"
    ]


def test_empty_view_payload_uses_legacy_resource_fallback():
    calls = []

    def request_fn(method, path, *, base_url, headers, payload=None, params=None):
        calls.append((method, path, payload, params))
        if method == "GET" and path == "/nodes/res-1":
            return {
                "id": "res-1",
                "name": "vm-1",
                "componentType": "resource.iaas.machine.instance.vsphere",
            }
        if method == "GET" and path == "/nodes/res-1/details":
            return {}
        return {}

    records = list_resource.load_resource_records(
        ["res-1"],
        base_url="https://cmp.example/platform-api",
        headers={},
        request_fn=request_fn,
    )

    assert calls == [
        ("PATCH", "/nodes/res-1/view", None, None),
        ("GET", "/nodes/res-1", None, None),
        ("GET", "/nodes/res-1/details", None, None),
    ]
    assert records[0]["fetchStatus"] == "ok"
    assert records[0]["missingEvidence"] == []
    assert records[0]["data"]["name"] == "vm-1"
    assert records[0]["errors"] == [
        "Primary PATCH /nodes/res-1/view did not return resource data."
    ]


def test_view_and_legacy_fallback_failure_reports_missing_evidence():
    calls = []

    def request_fn(method, path, *, base_url, headers, payload=None, params=None):
        calls.append((method, path, payload, params))
        if method == "PATCH" and path == "/nodes/res-1/view":
            raise RuntimeError("HTTP 400: No value present")
        if method == "GET" and path == "/nodes/res-1":
            raise RuntimeError("HTTP 404: missing")
        raise AssertionError(f"Unexpected call: {method} {path}")

    records = list_resource.load_resource_records(
        ["res-1"],
        base_url="https://cmp.example/platform-api",
        headers={},
        request_fn=request_fn,
    )

    assert calls == [
        ("PATCH", "/nodes/res-1/view", None, None),
        ("GET", "/nodes/res-1", None, None),
    ]
    assert records[0]["fetchStatus"] == "error"
    assert records[0]["missingEvidence"] == ["resource.data"]
    assert records[0]["data"] == {}
    assert records[0]["fallbackUsed"] is True
    assert records[0]["errors"] == [
        "Primary PATCH /nodes/res-1/view failed: HTTP 400: No value present",
        "Fallback GET /nodes/res-1 failed: HTTP 404: missing",
    ]


def test_view_wrapper_payload_becomes_resource_data():
    def request_fn(method, path, *, base_url, headers, payload=None, params=None):
        assert method == "PATCH"
        assert path == "/nodes/res-1/view"
        return {
            "data": {
                "id": "res-1",
                "name": "vm-1",
                "componentType": "resource.iaas.machine.instance.vsphere",
            }
        }

    records = list_resource.load_resource_records(
        ["res-1"],
        base_url="https://cmp.example/platform-api",
        headers={},
        request_fn=request_fn,
    )

    assert records[0]["data"] == {
        "id": "res-1",
        "name": "vm-1",
        "componentType": "resource.iaas.machine.instance.vsphere",
    }
    assert records[0]["normalized"]["type"] == "resource.iaas.machine.instance.vsphere"
