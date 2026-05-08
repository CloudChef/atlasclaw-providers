# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "approval"
    / "scripts"
    / "get_request_detail.py"
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def _load_module(monkeypatch):
    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=token")
    scripts_dir = str(SCRIPT_PATH.parent)
    inserted = False
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        inserted = True
    try:
        spec = importlib.util.spec_from_file_location("smartcmp_get_request_detail_script", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(scripts_dir)


def test_detail_uses_language_neutral_labels_and_extensible_resource_specs(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    monkeypatch.setattr(module.time, "time", lambda: 1_772_000_120)
    monkeypatch.setattr(sys, "argv", ["get_request_detail.py", "RES20260427000004"])

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        if url.endswith("/flavors"):
            return _FakeResponse({"content": []})
        assert url.endswith("/generic-request/current-activity-approval")
        assert params["sort"] == "updatedDate,desc"
        return _FakeResponse(
            {
                "content": [
                    {
                        "id": "internal-request-uuid",
                        "workflowId": "RES20260427000004",
                        "name": "Linux-test-agent",
                        "catalogName": "Linux VM",
                        "applicant": "Admin User",
                        "email": "admin@cmp.com",
                        "createdDate": 1_772_000_000_000,
                        "updatedDate": 1_772_000_060_000,
                        "currentActivity": {
                            "id": "approval-uuid",
                            "taskId": "task-uuid",
                            "processInstanceId": "process-uuid",
                            "processStep": {"name": "Level 1 Approval"},
                            "requestParams": {
                                "extensibleParameters": {
                                    "node_1": {
                                        "memory": {"value": 1024},
                                        "cloudEntryType": {"value": "aliyun"},
                                    }
                                },
                            },
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        module.main()

    rendered = stdout.getvalue()
    assert "Request ID: RES20260427000004" in rendered
    assert "编号:" not in rendered
    assert "memory=1024" in rendered
    assert "resource_type=aliyun" in rendered
    assert "no_detailed_specs" not in rendered
    assert "process-uuid" not in rendered
    assert "task-uuid" not in rendered
    assert "internal-request-uuid" not in rendered

    payload = stderr.getvalue().split("##APPROVAL_DETAIL_META_START##\n", 1)[1].split(
        "\n##APPROVAL_DETAIL_META_END##",
        1,
    )[0]
    meta = json.loads(payload)
    assert meta["requestId"] == "RES20260427000004"
    assert meta["resourceSpecs"][:3] == [
        "memory=1024",
        "resource_type=aliyun",
    ]
    for internal_field in ("approvalId", "internalRequestId", "workflowId", "taskId", "processInstanceId"):
        assert internal_field not in meta


def test_detail_returns_empty_resource_specs_when_request_has_no_specs(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    monkeypatch.setattr(module.time, "time", lambda: 1_772_000_120)
    monkeypatch.setattr(sys, "argv", ["get_request_detail.py", "TIC20260427000005"])

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        if url.endswith("/flavors"):
            return _FakeResponse({"content": []})
        assert url.endswith("/generic-request/current-activity-approval")
        return _FakeResponse(
            {
                "content": [
                    {
                        "workflowId": "TIC20260427000005",
                        "name": "General ticket",
                        "catalogName": "General Request",
                        "createdDate": 1_772_000_000_000,
                        "updatedDate": 1_772_000_060_000,
                        "currentActivity": {"requestParams": {}},
                    }
                ],
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        module.main()

    rendered = stdout.getvalue()
    assert "Resource Specs:" in rendered
    assert "no_detailed_specs" not in rendered

    payload = stderr.getvalue().split("##APPROVAL_DETAIL_META_START##\n", 1)[1].split(
        "\n##APPROVAL_DETAIL_META_END##",
        1,
    )[0]
    meta = json.loads(payload)
    assert meta["resourceSpecs"] == []


def test_detail_prefers_current_selection_name_over_memory(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    monkeypatch.setattr(module.time, "time", lambda: 1_772_000_120)
    monkeypatch.setattr(sys, "argv", ["get_request_detail.py", "RES20260505000029"])

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        if url.endswith("/flavors"):
            return _FakeResponse({"content": []})
        assert url.endswith("/generic-request/current-activity-approval")
        return _FakeResponse(
            {
                "content": [
                    {
                        "workflowId": "RES20260505000029",
                        "name": "my-linux-vm",
                        "catalogName": "Linux VM",
                        "createdDate": 1_772_000_000_000,
                        "updatedDate": 1_772_000_060_000,
                        "currentActivity": {
                            "requestParams": {
                                "resourceSpecs": {
                                    "node_1": {
                                        "selectedProfile": {
                                            "label": "Current Selection",
                                            "value": "Small,1vCPU,2GB",
                                        },
                                        "memory": {"value": 2048},
                                    }
                                }
                            }
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        module.main()

    rendered = stdout.getvalue()
    assert "- Small" in rendered
    assert "memory=2048" not in rendered

    payload = stderr.getvalue().split("##APPROVAL_DETAIL_META_START##\n", 1)[1].split(
        "\n##APPROVAL_DETAIL_META_END##",
        1,
    )[0]
    meta = json.loads(payload)
    assert meta["resourceSpecs"] == ["Small"]


def test_detail_prefers_flavor_name_from_compute_profile_id(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    monkeypatch.setattr(module.time, "time", lambda: 1_772_000_120)
    monkeypatch.setattr(sys, "argv", ["get_request_detail.py", "RES20260505000029"])
    compute_profile_id = "306ddaa2-711a-4ec0-8c1c-b512eb80d180"
    stale_flavor_id = "c8e8311d-3feb-4292-aa73-c3e542f93099"

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        if url.endswith("/flavors"):
            return _FakeResponse(
                {
                    "content": [
                        {"id": compute_profile_id, "name": "Medium"},
                        {"id": stale_flavor_id, "name": "Small"},
                    ]
                }
            )
        assert url.endswith("/generic-request/current-activity-approval")
        return _FakeResponse(
            {
                "content": [
                    {
                        "workflowId": "RES20260505000029",
                        "name": "my-linux-vm",
                        "catalogName": "Linux VM",
                        "createdDate": 1_772_000_000_000,
                        "updatedDate": 1_772_000_060_000,
                        "currentActivity": {
                            "requestParams": {
                                "extensibleParameters": {
                                    "Compute": {
                                        "compute_profile_id": {"value": compute_profile_id},
                                        "flavor_id": {"value": stale_flavor_id},
                                        "cpus": {"value": 1},
                                        "memory": {"value": 2048},
                                    }
                                }
                            }
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        module.main()

    rendered = stdout.getvalue()
    assert "- Medium" in rendered
    assert "- Small" not in rendered
    assert "memory=2048" not in rendered

    payload = stderr.getvalue().split("##APPROVAL_DETAIL_META_START##\n", 1)[1].split(
        "\n##APPROVAL_DETAIL_META_END##",
        1,
    )[0]
    meta = json.loads(payload)
    assert meta["resourceSpecs"] == ["Medium"]


def test_detail_returns_empty_specs_when_compute_profile_name_cannot_be_resolved(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    monkeypatch.setattr(module.time, "time", lambda: 1_772_000_120)
    monkeypatch.setattr(sys, "argv", ["get_request_detail.py", "RES20260505000029"])
    called_urls: list[str] = []

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        called_urls.append(url)
        if url.endswith("/flavors"):
            return _FakeResponse({"content": []})
        assert url.endswith("/generic-request/current-activity-approval")
        return _FakeResponse(
            {
                "content": [
                    {
                        "workflowId": "RES20260505000029",
                        "name": "my-linux-vm",
                        "catalogName": "Linux VM",
                        "createdDate": 1_772_000_000_000,
                        "updatedDate": 1_772_000_060_000,
                        "currentActivity": {
                            "requestParams": {
                                "extensibleParameters": {
                                    "Compute": {
                                        "compute_profile_id": {"value": "profile-1"},
                                        "memory": {"value": 2048},
                                    }
                                }
                            }
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        module.main()

    rendered = stdout.getvalue()
    payload = stderr.getvalue().split("##APPROVAL_DETAIL_META_START##\n", 1)[1].split(
        "\n##APPROVAL_DETAIL_META_END##",
        1,
    )[0]
    meta = json.loads(payload)

    assert any(url.endswith("/flavors") for url in called_urls)
    assert "memory=2048" not in rendered
    assert meta["resourceSpecs"] == []


def test_detail_maps_top_level_compute_profile_id_to_flavor_name(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    item = {
        "currentActivity": {
            "requestParams": {
                "_ra_Compute_compute_profile_id": "profile-1",
            }
        }
    }

    assert module._extract_resource_specs(
        item,
        flavor_names_by_id={"profile-1": "Small"},
    ) == ["Small"]


def test_detail_reads_current_approver_from_approval_requests(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    monkeypatch.setattr(module.time, "time", lambda: 1_778_135_300)
    monkeypatch.setattr(sys, "argv", ["get_request_detail.py", "RES20260507000015"])

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        if url.endswith("/flavors"):
            return _FakeResponse({"content": []})
        assert url.endswith("/generic-request/current-activity-approval")
        return _FakeResponse(
            {
                "content": [
                    {
                        "workflowId": "RES20260507000015",
                        "name": "test_vm_2019",
                        "catalogName": "Windows VM 2019",
                        "applicant": "平台管理员",
                        "createdDate": 1_778_135_283_182,
                        "updatedDate": 1_778_135_294_244,
                        "currentActivity": {
                            "processStep": {"name": "一级审批"},
                            "approvalRequests": [
                                {"approver": {"name": "user1", "loginId": "user1"}},
                                {"approver": {"name": "平台管理员", "loginId": "admin"}},
                            ],
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        module.main()

    rendered = stdout.getvalue()
    assert "Current Approver: user1, 平台管理员" in rendered

    payload = stderr.getvalue().split("##APPROVAL_DETAIL_META_START##\n", 1)[1].split(
        "\n##APPROVAL_DETAIL_META_END##",
        1,
    )[0]
    meta = json.loads(payload)
    assert meta["currentApprover"] == "user1, 平台管理员"
    assert meta["approvalStep"] == "一级审批"


def test_detail_rejects_internal_uuid_before_http(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    internal_id = "15919c7d-67c4-45a6-8603-91c6f6b9e644"
    monkeypatch.setattr(sys, "argv", ["get_request_detail.py", internal_id])

    def unexpected_http_call(*args, **kwargs):
        raise AssertionError("Unexpected HTTP call.")

    monkeypatch.setattr(module.requests, "get", unexpected_http_call)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            module.main()
        except SystemExit as exc:
            assert exc.code == 1

    rendered = stdout.getvalue()
    assert "[ERROR] Invalid SmartCMP Request ID." in rendered
    assert "RES20260505000010" in rendered
    assert internal_id not in rendered
    assert "APPROVAL_DETAIL_META" not in stderr.getvalue()
