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

import analyze_recommendation as analyzer  # noqa: E402
from requests import RequestException


def _make_resource_records() -> list[dict]:
    return [
        {
            "resourceId": "resource-001",
            "summary": {
                "name": "vm-prod-01",
                "resourceType": "VirtualMachine",
                "componentType": "cloudchef.nodes.Compute",
                "status": "RUNNING",
                "osType": "Linux",
                "osDescription": "Ubuntu 22.04",
            },
            "resource": {"name": "vm-prod-01"},
            "normalized": {
                "type": "cloudchef.nodes.Compute",
                "properties": {"instanceType": "c6.large"},
            },
            "fetchStatus": "ok",
            "errors": [],
        }
    ]


def test_build_analysis_payload_contains_required_sections():
    payload = analyzer.build_analysis_payload(
        violation={
            "id": "vio-1",
            "policyId": "pol-1",
            "policyName": "Idle VM",
            "resourceName": "vm-prod-01",
            "status": "OPEN",
            "monthlySaving": "80.25",
            "monthlyCost": "120.50",
            "savingOperationType": "STOP_IDLE",
            "fixType": "DAY2",
            "taskDefinition": {"name": "Stop VM"},
        },
        policy={
            "id": "pol-1",
            "name": "Idle VM",
            "description": "Stop low-utilization VM",
            "remedie": "Stop the instance",
        },
        saving_summary={"optimizableAmount": 1000},
        operation_summary={"STOP_IDLE": 12},
    )

    assert payload["violationId"] == "vio-1"
    assert set(payload) == {"violationId", "facts", "assessment", "recommendations", "suggestedNextStep"}
    assert payload["facts"]["policyName"] == "Idle VM"
    assert payload["facts"]["monthlySaving"] == 80.25
    assert payload["assessment"]["optimizationTheme"] == "idle_shutdown"
    assert payload["assessment"]["executionReadiness"] == "ready"
    assert payload["assessment"]["taskDefinitionPresent"] is True
    assert payload["assessment"]["savingSummaryAvailable"] is True
    assert payload["assessment"]["operationSummaryAvailable"] is True
    assert payload["suggestedNextStep"] == "execute_fix"
    assert "taskDefinitionPresent" not in payload["facts"]


def test_build_analysis_payload_merges_resource_context():
    payload = analyzer.build_analysis_payload(
        violation={
            "id": "vio-ctx",
            "policyId": "pol-1",
            "policyName": "Idle VM",
            "resourceId": "resource-001",
            "resourceName": "",
            "status": "OPEN",
            "monthlySaving": "80.25",
            "monthlyCost": "120.50",
            "savingOperationType": "STOP_IDLE",
        },
        policy={"id": "pol-1", "name": "Idle VM"},
        resource_records=_make_resource_records(),
    )

    assert payload["facts"]["resourceName"] == "vm-prod-01"
    assert payload["facts"]["componentType"] == "cloudchef.nodes.Compute"
    assert payload["facts"]["resourceStatus"] == "RUNNING"
    assert payload["facts"]["resourceContextAvailable"] is True
    assert payload["facts"]["resourceContext"]["resolvedCount"] == 1
    assert payload["facts"]["resourceContext"]["resources"][0]["normalized"]["properties"]["instanceType"] == "c6.large"
    assert payload["assessment"]["resourceContextAvailable"] is True
    assert payload["assessment"]["resourceFetchStatus"] == "ok"


def test_safe_load_resource_records_falls_back_to_resource_name(monkeypatch):
    def fake_load_resource_records(resource_ids, **_kwargs):
        resource_id = resource_ids[0]
        if resource_id == "missing-resource":
            return [
                {
                    "resourceId": resource_id,
                    "summary": {},
                    "resource": {},
                    "normalized": {"type": "", "properties": {}},
                    "fetchStatus": "not_found",
                    "errors": ["Resource was not returned by /nodes/search."],
                }
            ]
        return [
            {
                "resourceId": resource_id,
                "summary": {
                    "name": "vm-prod-01",
                    "resourceType": "VirtualMachine",
                    "componentType": "cloudchef.nodes.Compute",
                    "status": "RUNNING",
                    "osType": "Linux",
                    "osDescription": "Ubuntu 22.04",
                },
                "resource": {"name": "vm-prod-01"},
                "normalized": {
                    "type": "cloudchef.nodes.Compute",
                    "properties": {"instanceType": "c6.large"},
                },
                "fetchStatus": "ok",
                "errors": [],
            }
        ]

    monkeypatch.setattr(analyzer, "load_resource_records", fake_load_resource_records)
    monkeypatch.setattr(
        analyzer,
        "search_resource_summaries",
        lambda **_kwargs: [
            {
                "id": "resolved-resource",
                "name": "vm-prod-01",
                "resourceType": "VirtualMachine",
                "componentType": "cloudchef.nodes.Compute",
                "status": "RUNNING",
                "osType": "Linux",
                "osDescription": "Ubuntu 22.04",
                "externalId": "vm-001",
                "nodeInstanceId": "Compute_abc123",
            }
        ],
    )

    resource_records = analyzer._safe_load_resource_records(
        {
            "resourceId": "missing-resource",
            "resourceName": "vm-prod-01",
        },
        base_url="https://cmp.example.com/platform-api",
        headers={"CloudChef-Authenticate": "token"},
    )

    assert resource_records[0]["fetchStatus"] == "not_found"
    assert resource_records[1]["resourceId"] == "resolved-resource"
    assert resource_records[1]["fetchStatus"] == "ok"


def test_build_analysis_payload_prefers_resolved_resource_id_after_fallback_lookup():
    payload = analyzer.build_analysis_payload(
        violation={
            "id": "vio-ctx",
            "policyId": "pol-1",
            "policyName": "Idle VM",
            "resourceId": "missing-resource",
            "resourceName": "",
            "status": "OPEN",
        },
        policy={"id": "pol-1", "name": "Idle VM"},
        resource_records=[
            {
                "resourceId": "resolved-resource",
                "summary": {
                    "name": "vm-prod-01",
                    "resourceType": "VirtualMachine",
                    "componentType": "cloudchef.nodes.Compute",
                    "status": "RUNNING",
                    "osType": "Linux",
                    "osDescription": "Ubuntu 22.04",
                },
                "resource": {"name": "vm-prod-01"},
                "normalized": {
                    "type": "cloudchef.nodes.Compute",
                    "properties": {"instanceType": "c6.large"},
                },
                "fetchStatus": "ok",
                "errors": [],
            }
        ],
    )

    assert payload["facts"]["resourceId"] == "resolved-resource"
    assert payload["facts"]["resourceContext"]["requestedResourceIds"] == [
        "missing-resource",
        "resolved-resource",
    ]


def test_render_analysis_outputs_human_summary_and_structured_block():
    payload = {
        "violationId": "vio-1",
        "facts": {
            "resourceName": "vm-prod-01",
            "monthlySaving": 80.25,
        },
        "assessment": {
            "optimizationTheme": "idle_shutdown",
            "executionReadiness": "ready",
        },
        "recommendations": [],
        "suggestedNextStep": "manual_review",
    }

    output = analyzer.render_analysis(payload)

    assert "Violation vio-1: ready" in output
    assert "Theme: idle_shutdown" in output
    assert "Resource: vm-prod-01" in output
    assert "Estimated monthly saving: ¥80.25" in output
    assert "##COST_ANALYSIS_START##" in output
    assert "##COST_ANALYSIS_END##" in output

    meta_text = output.split("##COST_ANALYSIS_START##\n", 1)[1].split(
        "\n##COST_ANALYSIS_END##",
        1,
    )[0]
    assert json.loads(meta_text) == payload


def test_build_analysis_payload_flags_missing_repair_action():
    payload = analyzer.build_analysis_payload(
        violation={
            "id": "vio-2",
            "policyId": "policy.cost-optimization.machine.downgrade",
            "policyName": "policy.cost-optimization.machine.downgrade.name",
            "resourceName": "vm-demo-01",
            "status": "ACTIVED",
            "monthlySaving": None,
            "monthlyCost": None,
            "fixType": None,
            "taskDefinition": None,
            "remedie": "policy.cost-optimization.machine.downgrade.remedie",
        },
        policy={
            "id": "policy.cost-optimization.machine.downgrade",
            "name": "policy.cost-optimization.machine.downgrade.name",
            "description": "policy.cost-optimization.machine.downgrade.description",
            "remedie": "policy.cost-optimization.machine.downgrade.remedie",
        },
    )

    assert payload["assessment"]["executionReadiness"] == "manual_review"
    assert payload["assessment"]["taskDefinitionPresent"] is False
    assert payload["suggestedNextStep"] == "configure_platform_policy"
    assert payload["recommendations"][0]["platformExecutable"] is False
    assert "no repair action configured" in payload["recommendations"][0]["reason"]


def test_safe_get_json_returns_none_on_request_exception(monkeypatch):
    def raise_request_error(*_args, **_kwargs):
        raise RequestException("boom")

    monkeypatch.setattr(analyzer.requests, "get", raise_request_error)

    assert analyzer.safe_get_json("https://cmp.example.com/test", headers={}) is None


def test_safe_get_json_returns_none_on_invalid_json(monkeypatch):
    class InvalidJsonResponse:
        status_code = 200

        def json(self):
            raise ValueError("invalid json")

    monkeypatch.setattr(analyzer.requests, "get", lambda *args, **kwargs: InvalidJsonResponse())

    assert analyzer.safe_get_json("https://cmp.example.com/test", headers={}) is None
