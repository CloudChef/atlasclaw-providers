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
APPROVAL_CONTEXT_PATH = SCRIPT_PATH.parent / "_approval_context.py"


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def localized(default: str, zh_cn: str) -> dict[str, object]:
    return {
        "default": default,
        "translations": {
            "en-US": default,
            "zh-CN": zh_cn,
        },
    }


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


def _load_approval_context_module():
    scripts_dir = str(APPROVAL_CONTEXT_PATH.parent)
    inserted = False
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        inserted = True
    try:
        spec = importlib.util.spec_from_file_location("smartcmp_approval_context_script", APPROVAL_CONTEXT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
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
                        "catalogId": "catalog-linux",
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
                        "exts": {
                            "approval_state": "PENDING",
                            "approval_type": "PROVISION_BP",
                            "approval_id": "approval-uuid",
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
    expected_href = (
        "https://cmp.example.com/#/main/new-application/"
        "pendingApproval/PROVISION_BP/approval-uuid?from=normal&fromPagePartUrl=SR_MY_APPROVAL"
    )
    assert meta["object_type"] == "approval_request"
    assert meta["object_id"] == "RES20260427000004"
    assert meta["object_name"] == "Linux-test-agent"
    assert [action["display_label"] for action in meta["object_actions"]] == [
        localized("Open", "打开"),
        localized("Analyze", "分析"),
        localized("Approve", "同意"),
        localized("Reject", "拒绝"),
    ]
    assert meta["object_actions"][0]["href"] == expected_href
    assert meta["object_actions"][1]["agent_prompt"] == localized(
        "Run read-only approval analysis for RES20260427000004",
        "只读分析审批请求 RES20260427000004",
    )
    assert meta["object_actions"][2]["agent_prompt"] == localized(
        "Approve RES20260427000004; the user confirmed this approval in the UI.",
        "批准 RES20260427000004，用户已在界面确认执行。",
    )
    assert meta["object_actions"][2]["confirmation_message"] == localized(
        "Confirm approving RES20260427000004?",
        "确认同意 RES20260427000004？",
    )
    assert meta["object_actions"][2]["requires_confirmation"] is True
    assert meta["object_actions"][3]["agent_prompt_template"] == localized(
        (
            "Reject RES20260427000004, reason: {{reason}}; "
            "the user confirmed this rejection in the UI."
        ),
        "拒绝 RES20260427000004，原因：{{reason}}，用户已在界面确认执行。",
    )
    assert meta["object_actions"][3]["confirmation_message"] == localized(
        "Provide a rejection reason for RES20260427000004.",
        "请填写拒绝 RES20260427000004 的原因。",
    )
    assert meta["object_actions"][3]["inputs"][0]["name"] == "reason"
    assert meta["object_actions"][3]["inputs"][0]["display_label"] == localized(
        "Rejection reason",
        "拒绝原因",
    )
    assert expected_href not in rendered
    assert meta["catalogId"] == "catalog-linux"
    assert meta["requestParams"]["extensibleParameters"]["node_1"]["memory"]["value"] == 1024
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
    assert "Resource Specs:" not in rendered
    assert "no_detailed_specs" not in rendered

    payload = stderr.getvalue().split("##APPROVAL_DETAIL_META_START##\n", 1)[1].split(
        "\n##APPROVAL_DETAIL_META_END##",
        1,
    )[0]
    meta = json.loads(payload)
    assert meta["resourceSpecs"] == []
    assert [action["display_label"] for action in meta["object_actions"]] == [
        localized("Analyze", "分析"),
        localized("Approve", "同意"),
        localized("Reject", "拒绝"),
    ]
    assert meta["object_actions"][0]["agent_prompt"] == localized(
        "Run read-only approval analysis for TIC20260427000005",
        "只读分析审批请求 TIC20260427000005",
    )
    assert meta["object_actions"][1]["agent_prompt"] == localized(
        "Approve TIC20260427000005; the user confirmed this approval in the UI.",
        "批准 TIC20260427000005，用户已在界面确认执行。",
    )
    assert meta["object_actions"][2]["agent_prompt_template"] == localized(
        (
            "Reject TIC20260427000005, reason: {{reason}}; "
            "the user confirmed this rejection in the UI."
        ),
        "拒绝 TIC20260427000005，原因：{{reason}}，用户已在界面确认执行。",
    )


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
    assert "Resource Specs: Small" in rendered
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
    assert "Resource Specs: Medium" in rendered
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
    context_module = _load_approval_context_module()
    item = {
        "currentActivity": {
            "requestParams": {
                "_ra_Compute_compute_profile_id": "profile-1",
            }
        }
    }

    assert context_module.extract_resource_specs(
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
