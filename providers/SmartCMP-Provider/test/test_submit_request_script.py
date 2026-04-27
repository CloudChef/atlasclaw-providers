# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import io
import json
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
    / "request"
    / "scripts"
    / "submit.py"
)


class FakeResponse:
    def __init__(self, payload, *, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload


def _unexpected_http_call(*args, **kwargs):
    raise AssertionError("Unexpected HTTP call in test.")


def run_script(monkeypatch, argv: list[str], *, fake_post=None, fake_get=None):
    module_name = "test_submit_request_script_module"

    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=test-token")
    monkeypatch.setenv("CMP_SUBMIT_VERIFY_ATTEMPTS", "1")
    monkeypatch.setenv("CMP_SUBMIT_VERIFY_INTERVAL_SECONDS", "0")
    monkeypatch.setattr(requests, "post", fake_post or _unexpected_http_call)
    monkeypatch.setattr(requests, "get", fake_get or _unexpected_http_call)
    monkeypatch.setattr(sys, "argv", [SCRIPT_PATH.name, *argv])

    stdout = io.StringIO()
    stderr = io.StringIO()
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    exit_code = 0
    try:
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                spec.loader.exec_module(module)
        except SystemExit as exc:
            exit_code = int(exc.code or 0)
    finally:
        sys.modules.pop(module_name, None)

    return exit_code, stdout.getvalue(), stderr.getvalue()


def test_submit_request_fails_when_verified_request_enters_failed_state(monkeypatch):
    def fake_post(url, headers=None, json=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/generic-request/submit"
        return FakeResponse([{"id": "req-1", "workflowId": "TIC20260422000001", "state": "INITIALING"}])

    def fake_get(url, headers=None, verify=None, timeout=None):
        if url == "https://cmp.example.com/platform-api/generic-request/req-1":
            return FakeResponse(
                {
                    "id": "req-1",
                    "name": "vm-1",
                    "catalogName": "Linux OS",
                    "businessGroupId": "bg-1",
                    "state": "INITIALING_FAILED",
                    "provisionState": "provisionAllocationFailed",
                    "errMsg": "No value present",
                    "catalogServiceRequest": {
                        "requestParameters": {
                            "cloud_resource_facets": {"FACET_ENV": ["uat", "test"]},
                            "extensibleParameters": [
                                {
                                    "Compute": {
                                        "resource_bundle_config": {
                                            "policy_type": {"value": "RB_POLICY_STATIC"},
                                            "policy_resource": {"value": "rb-1"},
                                        },
                                        "compute_profile_id": {"value": "profile-1"},
                                        "flavor_id": {"value": "ecs.n4.small"},
                                        "logic_template_id": {"value": "lt-1"},
                                        "template_id": {"value": "vm-121"},
                                        "network_id": {"value": "network-78"},
                                        "cpus": {"value": 2},
                                        "memory": {"value": 4},
                                        "system_disk_config": {"value": {"size": 50}},
                                        "credential": {"user": "root"},
                                    }
                                }
                            ],
                        }
                    },
                }
            )
        if url == "https://cmp.example.com/platform-api/business-groups/bg-1":
            return FakeResponse({"id": "bg-1", "name": "测试", "code": "0003"})
        if url == "https://cmp.example.com/platform-api/resource-bundles/rb-1":
            return FakeResponse(
                {
                    "id": "rb-1",
                    "name": "vSphere资源池",
                    "facets": ["FACET_ENV:uat"],
                    "cloudEntryTypeId": "yacmp:cloudentry:type:vsphere",
                    "enabled": True,
                    "global": True,
                }
            )
        raise AssertionError(f"Unexpected GET url: {url}")

    exit_code, stdout, _ = run_script(
        monkeypatch,
        ["--json", '{"catalogName":"Linux OS","name":"vm-1","resourceSpecs":[{}]}'],
        fake_post=fake_post,
        fake_get=fake_get,
    )

    assert exit_code == 1
    assert "[FAILED] Request was created but initialization failed" in stdout
    assert "Request ID: TIC20260422000001" in stdout
    assert "State: INITIALING_FAILED" in stdout
    assert "Provision State: provisionAllocationFailed" in stdout
    assert "Error: No value present" in stdout
    assert "Diagnosis:" in stdout
    assert "Catalog: Linux OS" in stdout
    assert "Request Name: vm-1" in stdout
    assert "Business Group: 测试 (bg-1)" in stdout
    assert "Requested Facets: FACET_ENV:uat, FACET_ENV:test" in stdout
    assert "Selected Resource Bundle: vSphere资源池 (rb-1)" in stdout
    assert "Resource Bundle Facets: FACET_ENV:uat" in stdout
    assert "Resource Bundle Policy: RB_POLICY_STATIC" in stdout
    assert "Compute Profile ID: profile-1" in stdout
    assert "Flavor ID: ecs.n4.small" in stdout
    assert "Template ID: vm-121" in stdout
    assert "Logic Template ID: lt-1" in stdout
    assert "Network ID: network-78" in stdout
    assert "Requested Shape: CPU=2, Memory=4" in stdout
    assert "System Disk Size: 50" in stdout
    assert "Credential User: root" in stdout


def test_submit_request_succeeds_when_verified_request_is_visible(monkeypatch):
    def fake_post(url, headers=None, json=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/generic-request/submit"
        return FakeResponse([{"id": "req-1", "workflowId": "TIC20260422000002", "state": "INITIALING"}])

    def fake_get(url, headers=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/generic-request/req-1"
        return FakeResponse(
            {
                "id": "req-1",
                "workflowId": "TIC20260422000002",
                "state": "INITIALING",
                "processInstanceId": "proc-1",
            }
        )

    exit_code, stdout, _ = run_script(
        monkeypatch,
        ["--json", '{"catalogName":"Linux OS","name":"vm-1","resourceSpecs":[{}]}'],
        fake_post=fake_post,
        fake_get=fake_get,
    )

    assert exit_code == 0
    assert "[SUCCESS] Request submitted" in stdout
    assert "Request ID: TIC20260422000002" in stdout
    assert "State: INITIALING" in stdout
    assert "Catalog: Linux OS" in stdout
    assert "Name: vm-1" in stdout


def test_submit_request_stays_pending_without_error_when_request_never_leaves_initialing(monkeypatch):
    def fake_post(url, headers=None, json=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/generic-request/submit"
        return FakeResponse([{"id": "req-1", "workflowId": "TIC20260422000003", "state": "INITIALING"}])

    def fake_get(url, headers=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/generic-request/req-1"
        return FakeResponse(
            {
                "id": "req-1",
                "state": "INITIALING",
                "provisionState": "",
                "processInstanceId": "",
            }
        )

    exit_code, stdout, _ = run_script(
        monkeypatch,
        ["--json", '{"catalogName":"Linux OS","name":"vm-1","resourceSpecs":[{}]}'],
        fake_post=fake_post,
        fake_get=fake_get,
    )

    assert exit_code == 0
    assert "[PENDING] Request submitted, but workflow has not been confirmed yet" in stdout
    assert "Request ID: TIC20260422000003" in stdout
    assert "State: INITIALING" in stdout
    assert "Note: Track this request by Request ID instead of resubmitting it." in stdout


def test_submit_request_stays_pending_without_error_when_verification_lookup_fails(monkeypatch):
    def fake_post(url, headers=None, json=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/generic-request/submit"
        return FakeResponse([{"id": "req-1", "workflowId": "TIC20260422000004", "state": "INITIALING"}])

    def fake_get(url, headers=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/generic-request/req-1"
        return FakeResponse({"message": "Not found"}, status_code=404, text="Not found")

    exit_code, stdout, _ = run_script(
        monkeypatch,
        ["--json", '{"catalogName":"Linux OS","name":"vm-1","resourceSpecs":[{}]}'],
        fake_post=fake_post,
        fake_get=fake_get,
    )

    assert exit_code == 0
    assert "[PENDING] Request submitted, but not yet verifiable in SmartCMP" in stdout
    assert "Request ID: TIC20260422000004" in stdout
    assert "Submit State: INITIALING" in stdout
    assert "Verify HTTP: 404" in stdout
    assert "Message: Not found" in stdout
    assert "Note: Track this request by Request ID instead of resubmitting it." in stdout
