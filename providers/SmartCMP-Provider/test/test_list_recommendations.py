# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "cost-optimization"
    / "scripts"
)
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import list_recommendations as listing  # noqa: E402


def localized(default: str, zh_cn: str) -> dict[str, object]:
    return {
        "default": default,
        "translations": {
            "en-US": default,
            "zh-CN": zh_cn,
        },
    }


def test_render_output_formats_summary_and_meta_block():
    items = [
        {
            "id": "vio-1",
            "policyId": "pol-1",
            "policyName": "Idle VM",
            "resourceId": "res-1",
            "resourceName": "vm-prod-01",
            "status": "OPEN",
            "severity": "HIGH",
            "category": "COST",
            "monthlyCost": "120.5",
            "monthlySaving": "80.25",
            "savingOperationType": "STOP_IDLE",
            "fixType": "DAY2",
            "taskInstanceId": "task-1",
            "lastExecuteDate": 1_710_000_000_000,
        }
    ]

    output = listing.render_output(items)

    assert "Found 1 cost optimization recommendation(s):" in output
    assert "| # | Resource | Policy | Status | Operation | Saving |" in output
    assert "| 1 | vm-prod-01 | Idle VM | OPEN | STOP_IDLE | 80.25 |" in output
    assert "##COST_RECOMMENDATION_META_START##" in output
    assert "##COST_RECOMMENDATION_META_END##" in output

    meta_text = output.split("##COST_RECOMMENDATION_META_START##\n", 1)[1].split(
        "\n##COST_RECOMMENDATION_META_END##",
        1,
    )[0]
    meta = json.loads(meta_text)
    assert meta[0]["index"] == 1
    assert meta[0]["violationId"] == "vio-1"
    assert meta[0]["policyId"] == "pol-1"
    assert meta[0]["policyName"] == "Idle VM"
    assert meta[0]["resourceId"] == "res-1"
    assert meta[0]["resourceName"] == "vm-prod-01"
    assert meta[0]["status"] == "OPEN"
    assert meta[0]["severity"] == "HIGH"
    assert meta[0]["category"] == "COST"
    assert meta[0]["monthlyCost"] == 120.5
    assert meta[0]["monthlySaving"] == 80.25
    assert meta[0]["savingOperationType"] == "STOP_IDLE"
    assert meta[0]["fixType"] == "DAY2"
    assert meta[0]["taskInstanceId"] == "task-1"
    assert meta[0]["lastExecuteDate"] == "2024-03-09T16:00:00Z"
    assert meta[0]["taskDefinitionId"] == ""
    assert meta[0]["taskDefinitionName"] == ""
    assert meta[0]["object_type"] == "cost_optimization_recommendation"
    assert meta[0]["object_id"] == "vio-1"
    assert meta[0]["object_name"] == "Idle VM"
    assert meta[0]["object_actions"] == [
        {
            "action_id": "view_detail",
            "kind": "agent_prompt",
            "display_label": localized("View details", "查看详情"),
            "agent_prompt": localized(
                "Analyze cost optimization recommendation vio-1",
                "分析成本优化建议 vio-1",
            ),
            "effect": "read",
            "tone": "default",
        }
    ]


def test_recommendation_open_resource_requires_known_resource_route():
    unknown_resource = listing.normalize_violation(
        {
            "id": "vio-1",
            "policyName": "Idle resource",
            "resourceId": "res-1",
            "resourceName": "resource-01",
        },
        1,
    )
    vm_resource = listing.normalize_violation(
        {
            "id": "vio-2",
            "policyName": "Idle VM",
            "resourceId": "vm-1",
            "resourceName": "vm-prod-01",
            "resourceType": "VirtualMachine",
        },
        2,
    )

    unknown_actions = listing.build_recommendation_object_actions(
        unknown_resource,
        base_url="https://cmp.example.com/platform-api",
    )
    vm_actions = listing.build_recommendation_object_actions(
        vm_resource,
        base_url="https://cmp.example.com/platform-api",
    )

    assert [action["action_id"] for action in unknown_actions] == ["view_detail"]
    assert vm_actions[1] == {
        "action_id": "open_resource",
        "kind": "open_url",
        "display_label": localized("Open resource", "打开资源"),
        "href": "https://cmp.example.com/#/main/virtual-machines/vm-1/details",
        "effect": "navigate",
        "tone": "default",
    }


def test_render_output_handles_empty_list():
    output = listing.render_output([])

    assert "No cost optimization recommendations found." in output
    meta_text = output.split("##COST_RECOMMENDATION_META_START##\n", 1)[1].split(
        "\n##COST_RECOMMENDATION_META_END##",
        1,
    )[0]
    assert json.loads(meta_text) == []


def test_main_defaults_to_latest_active_cost_optimization_results(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"content": []}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs["params"]
        return Response()

    monkeypatch.setattr(
        listing,
        "require_config",
        lambda: ("https://cmp.example/platform-api", "", {}, {}),
    )
    monkeypatch.setattr(listing.requests, "get", fake_get)
    monkeypatch.setattr(listing, "render_output", lambda *args, **kwargs: "")
    monkeypatch.setattr(sys, "argv", ["list_recommendations.py"])

    assert listing.main() == 0
    assert captured["url"] == "https://cmp.example/platform-api/compliance-policies/violations/search"
    assert captured["params"] == {
        "status": "ACTIVED",
        "category": "COST-OPTIMIZATION",
        "sort": "lastExecuteDate,desc",
        "page": 0,
        "size": 20,
        "queryValue": "",
    }
