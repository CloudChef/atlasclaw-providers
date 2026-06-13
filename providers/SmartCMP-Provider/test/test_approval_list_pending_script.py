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
    / "list_pending.py"
)


def _load_module():
    scripts_dir = str(SCRIPT_PATH.parent)
    inserted = False
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        inserted = True
    try:
        spec = importlib.util.spec_from_file_location("smartcmp_list_pending_script", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(scripts_dir)


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


def test_build_pending_query_params_defaults_to_all_pending() -> None:
    module = _load_module()

    params = module.build_pending_query_params(now_ms=1_700_000_000_000, days=None)

    assert params["page"] == 1
    assert params["size"] == 50
    assert params["stage"] == "pending"
    assert "startAtMin" not in params
    assert "startAtMax" not in params
    assert "rangeField" not in params


def test_build_pending_query_params_adds_time_window_when_days_specified() -> None:
    module = _load_module()

    now_ms = 1_700_000_000_000
    params = module.build_pending_query_params(now_ms=now_ms, days=7)

    assert params["stage"] == "pending"
    assert params["startAtMax"] == now_ms
    assert params["rangeField"] == "updatedDate"
    assert params["startAtMin"] < now_ms


def test_parse_days_from_argv_accepts_positive_integer_only() -> None:
    module = _load_module()

    assert module.parse_days_from_argv([]) is None
    assert module.parse_days_from_argv(["--days", "7"]) == 7
    assert module.parse_days_from_argv(["--days", "0"]) is None
    assert module.parse_days_from_argv(["--days", "-3"]) is None
    assert module.parse_days_from_argv(["--days", "abc"]) is None


def test_build_meta_exposes_only_canonical_request_id() -> None:
    module = _load_module()
    item = {
        "id": "internal-request-uuid",
        "workflowId": "RES20260427000004",
        "name": "Linux-test-agent",
        "createdDate": 1_772_000_000_000,
        "updatedDate": 1_772_000_060_000,
        "currentActivity": {
            "id": "approval-activity-uuid",
            "taskId": "task-uuid",
            "processInstanceId": "process-uuid",
        },
    }
    item["_priority"] = module.calculate_priority(item, now_ms=1_772_000_120_000)

    meta = module.build_meta([item], now_ms=1_772_000_120_000)

    assert meta[0]["requestId"] == "RES20260427000004"
    assert meta[0]["priority"] == "low"
    assert meta[0]["priorityFactors"] == []
    assert meta[0]["approvalStep"] == "step_unavailable"
    assert meta[0]["currentApprover"] == "approver_unavailable"
    assert meta[0]["costEstimate"] == "not_estimated"
    assert meta[0]["resourceSpecs"] == []
    for internal_field in ("id", "workflowId", "internalRequestId", "taskId", "processInstanceId"):
        assert internal_field not in meta[0]


def test_build_meta_accepts_request_id_alias_fields() -> None:
    module = _load_module()
    items = [
        {"requestId": "RES20260427000004"},
        {"customizedId": "TIC20260427000005"},
        {"currentActivity": {"workflowId": "CHG20260427000006"}},
    ]
    for item in items:
        item["_priority"] = module.calculate_priority(item, now_ms=1_772_000_120_000)

    meta = module.build_meta(items, now_ms=1_772_000_120_000)

    assert [item["requestId"] for item in meta] == [
        "RES20260427000004",
        "TIC20260427000005",
        "CHG20260427000006",
    ]
    assert [item["object_actions"][0]["agent_prompt"] for item in meta] == [
        localized(
            "Show approval details for RES20260427000004",
            "查看 RES20260427000004 的审批详情",
        ),
        localized(
            "Show approval details for TIC20260427000005",
            "查看 TIC20260427000005 的审批详情",
        ),
        localized(
            "Show approval details for CHG20260427000006",
            "查看 CHG20260427000006 的审批详情",
        ),
    ]


def test_build_meta_reads_current_approver_from_approval_requests() -> None:
    module = _load_module()
    item = {
        "workflowId": "RES20260507000015",
        "name": "test_vm_2019",
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
    item["_priority"] = module.calculate_priority(item, now_ms=1_778_135_300_000)

    meta = module.build_meta([item], now_ms=1_778_135_300_000)
    rendered = module.render_pending_table([item], total=1, now_ms=1_778_135_300_000)

    assert meta[0]["currentApprover"] == "user1, 平台管理员"
    assert "user1, 平台管理员" in rendered
    assert "approver_unavailable" not in rendered


def test_resource_specs_use_language_neutral_codes() -> None:
    module = _load_module()
    item = {
        "currentActivity": {
            "requestParams": {
                "quantity": 2,
                "resourceSpecs": {
                    "node_1": {
                        "cpu": 4,
                        "memory": 2048,
                        "disk": "100GB",
                        "cloudEntryType": {"value": "aliyun"},
                        "asset_tag": "asset-1",
                    }
                },
            }
        }
    }

    assert module.extract_resource_specs(item) == [
        "cpu_cores=4",
        "memory=2048",
        "storage=100GB",
        "resource_type=aliyun",
        "asset_tag=asset-1",
        "quantity=2",
    ]


def test_resource_specs_prefer_current_selection_name() -> None:
    module = _load_module()
    item = {
        "currentActivity": {
            "requestParams": {
                "resourceSpecs": {
                    "node_1": {
                        "currentSelection": "Small,1vCPU,2GB",
                        "cpu": 1,
                        "memory": 2048,
                    }
                }
            }
        }
    }

    assert module.extract_resource_specs(item) == ["Small"]


def test_resource_specs_prefer_flavor_name_from_compute_profile_id() -> None:
    module = _load_module()
    compute_profile_id = "306ddaa2-711a-4ec0-8c1c-b512eb80d180"
    stale_flavor_id = "c8e8311d-3feb-4292-aa73-c3e542f93099"
    item = {
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
        }
    }

    assert module.extract_resource_specs(
        item,
        flavor_names_by_id={compute_profile_id: "Medium", stale_flavor_id: "Small"},
    ) == ["Medium"]


def test_resource_specs_map_top_level_compute_profile_id_to_flavor_name() -> None:
    module = _load_module()
    item = {
        "currentActivity": {
            "requestParams": {
                "_ra_Compute_compute_profile_id": "profile-1",
            }
        }
    }

    assert module.extract_resource_specs(
        item,
        flavor_names_by_id={"profile-1": "Small"},
    ) == ["Small"]


def test_resource_specs_return_empty_for_unresolved_compute_profile_id() -> None:
    module = _load_module()
    item = {
        "currentActivity": {
            "requestParams": {
                "extensibleParameters": {
                    "Compute": {
                        "compute_profile_id": {"value": "profile-1"},
                        "memory": {"value": 2048},
                        "cpus": {"value": 1},
                    }
                }
            }
        }
    }

    assert module.extract_resource_specs(item, flavor_names_by_id={}) == []


def test_resource_specs_read_labeled_current_selection_value() -> None:
    module = _load_module()
    item = {
        "currentActivity": {
            "requestParams": {
                "resourceSpecs": {
                    "node_1": {
                        "selected": {
                            "label": "Current Selection",
                            "value": "Medium,2vCPU,4GB",
                        },
                        "memory": 4096,
                    }
                }
            }
        }
    }

    assert module.extract_resource_specs(item) == ["Medium"]


def test_main_renders_newest_first_table_and_hides_internal_meta(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(
        module,
        "require_config",
        lambda: ("https://cmp.example.com/platform-api", "token", {"Cookie": "token"}, None),
    )
    monkeypatch.setattr(module.time, "time", lambda: 1_772_000_120)
    called_urls: list[str] = []

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        called_urls.append(url)
        if url == "https://cmp.example.com/platform-api/flavors":
            return _FakeResponse({"content": []})
        assert url == "https://cmp.example.com/platform-api/generic-request/current-activity-approval"
        assert params["sort"] == "updatedDate,desc"
        return _FakeResponse(
            {
                "content": [
                    {
                        "id": "old-internal-request-uuid",
                        "workflowId": "RES20260426000003",
                        "name": "older urgent production request",
                        "catalogName": "General Ticket",
                        "applicant": "Admin User",
                        "createdDate": 1_771_900_000_000,
                        "updatedDate": 1_771_900_060_000,
                        "currentActivity": {
                            "id": "old-approval-uuid",
                            "taskId": "old-task-uuid",
                            "processInstanceId": "old-process-uuid",
                        },
                    },
                    {
                        "id": "new-internal-request-uuid",
                        "workflowId": "RES20260427000004",
                        "name": "Linux-test-agent",
                        "catalogName": "Linux VM",
                        "applicant": "Admin User",
                        "createdDate": 1_772_000_000_000,
                        "updatedDate": 1_772_000_060_000,
                        "currentActivity": {
                            "id": "new-approval-uuid",
                            "taskId": "new-task-uuid",
                            "processInstanceId": "new-process-uuid",
                        },
                    },
                ],
                "totalElements": 2,
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        assert module.main([]) == 0

    rendered = stdout.getvalue()
    internal = stderr.getvalue()
    assert "| # | Request ID | Name | Catalog | Applicant | Updated At | Approver |" in rendered
    assert "Wait(h)" not in rendered
    assert "Priority" not in rendered
    assert "Step" not in rendered
    assert "Specs" not in rendered
    assert rendered.index("RES20260427000004") < rendered.index("RES20260426000003")
    assert "new-internal-request-uuid" not in rendered
    assert "new-approval-uuid" not in rendered
    assert "new-task-uuid" not in rendered
    assert "new-process-uuid" not in rendered
    assert "##APPROVAL_META_START##" not in rendered
    assert "DISPLAY_META" not in internal

    payload = internal.split("##APPROVAL_META_START##\n", 1)[1].split(
        "\n##APPROVAL_META_END##",
        1,
    )[0]
    meta = json.loads(payload)
    assert [item["requestId"] for item in meta] == ["RES20260427000004", "RES20260426000003"]
    assert meta[0]["object_type"] == "approval_request"
    assert meta[0]["object_id"] == "RES20260427000004"
    assert meta[0]["object_name"] == "Linux-test-agent"
    assert [action["display_label"] for action in meta[0]["object_actions"]] == [
        localized("View details", "查看详情")
    ]
    assert meta[0]["object_actions"][0]["agent_prompt"] == localized(
        "Show approval details for RES20260427000004",
        "查看 RES20260427000004 的审批详情",
    )
    assert "https://cmp.example.com/#/main/service-request/my-approval" not in rendered
    assert meta[0]["priority"] == "low"
    assert meta[0]["priorityFactors"] == []
    assert meta[1]["priority"] == "high"
    assert meta[1]["priorityFactors"] == [
        "wait_over_24h",
        "matched_high_priority_keyword",
    ]
    for internal_field in ("id", "workflowId", "internalRequestId", "taskId", "processInstanceId"):
        assert internal_field not in meta[0]
    assert "https://cmp.example.com/platform-api/flavors" not in called_urls


def test_main_meta_derives_open_url_from_base_url_without_printing_raw_url(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(
        module,
        "require_config",
        lambda: (
            "https://cmp.example.com/platform-api",
            "token",
            {"Cookie": "token"},
            {
                "base_url": "https://cmp.example.com/platform-api",
            },
        ),
    )
    monkeypatch.setattr(module.time, "time", lambda: 1_772_000_120)

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/generic-request/current-activity-approval"
        return _FakeResponse(
            {
                "content": [
                    {
                        "id": "request-row-1",
                        "workflowId": "RES20260427000004",
                        "name": "Linux-test-agent",
                        "catalogName": "Linux VM",
                        "applicant": "Admin User",
                        "createdDate": 1_772_000_000_000,
                        "updatedDate": 1_772_000_060_000,
                        "exts": {
                            "approval_state": "PENDING",
                            "approval_type": "PROVISION_BP",
                            "approval_id": "approval-activity-1",
                        },
                    }
                ],
                "totalElements": 1,
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        assert module.main([]) == 0

    rendered = stdout.getvalue()
    payload = stderr.getvalue().split("##APPROVAL_META_START##\n", 1)[1].split(
        "\n##APPROVAL_META_END##",
        1,
    )[0]
    meta = json.loads(payload)
    expected_href = (
        "https://cmp.example.com/#/main/new-application/"
        "pendingApproval/PROVISION_BP/approval-activity-1?from=normal&fromPagePartUrl=SR_MY_APPROVAL"
    )
    assert meta[0]["object_actions"][1]["href"] == expected_href
    assert meta[0]["object_actions"][0]["agent_prompt"] == localized(
        "Show approval details for RES20260427000004",
        "查看 RES20260427000004 的审批详情",
    )
    assert expected_href not in rendered
    assert "https://cmp.example.com" not in rendered


def test_main_returns_empty_specs_when_compute_profile_name_cannot_be_resolved(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(
        module,
        "require_config",
        lambda: ("https://cmp.example.com/platform-api", "token", {"Cookie": "token"}, None),
    )
    monkeypatch.setattr(module.time, "time", lambda: 1_772_000_120)
    called_urls: list[str] = []

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        called_urls.append(url)
        if url == "https://cmp.example.com/platform-api/flavors":
            return _FakeResponse({"content": []})
        assert url == "https://cmp.example.com/platform-api/generic-request/current-activity-approval"
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
                "totalElements": 1,
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        assert module.main([]) == 0

    rendered = stdout.getvalue()
    payload = stderr.getvalue().split("##APPROVAL_META_START##\n", 1)[1].split(
        "\n##APPROVAL_META_END##",
        1,
    )[0]
    meta = json.loads(payload)

    assert "https://cmp.example.com/platform-api/flavors" in called_urls
    assert "memory=2048" not in rendered
    assert meta[0]["resourceSpecs"] == []
