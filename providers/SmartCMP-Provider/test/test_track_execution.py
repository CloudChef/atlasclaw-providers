# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import requests


SCRIPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "cost-optimization"
    / "scripts"
)
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import track_execution as tracker  # noqa: E402


class DummyResponse:
    def __init__(self, status_code=200, body=None, text="{}"):
        self.status_code = status_code
        self._body = {} if body is None else body
        self.text = text

    def json(self):
        return self._body


def test_build_tracking_summary_merges_sources_and_surfaces_failures():
    violation_instances = [
        tracker.normalize_violation_instance(
            {
                "id": "vio-inst-1",
                "violationId": "vio-1",
                "taskInstanceId": "exec-1",
                "resourceName": "vm-prod-01",
                "status": "FAILED",
                "violationMessage": "violation instance failed",
            }
        ),
        tracker.normalize_violation_instance(
            {
                "id": "vio-inst-2",
                "violationId": "vio-1",
                "taskInstanceId": "exec-2",
                "resourceName": "vm-prod-02",
                "status": "SUCCESS",
            }
        ),
    ]
    resource_executions = [
        tracker.normalize_resource_execution(
            {
                "id": "res-exec-1",
                "policyViolationId": "vio-1",
                "executionId": "exec-1",
                "resourceName": "vm-prod-01",
                "status": "FAILED",
                "errMsg": "resource execution failed",
            }
        ),
        tracker.normalize_resource_execution(
            {
                "id": "res-exec-2",
                "policyViolationId": "vio-1",
                "executionId": "exec-2",
                "resourceName": "vm-prod-02",
                "status": "SUCCESS",
            }
        ),
    ]

    summary = tracker.build_tracking_summary(
        violation_id="vio-1",
        violation_instances=violation_instances,
        resource_executions=resource_executions,
        resource_executions_available=True,
        warnings=["resource execution query completed"],
    )

    assert summary["overallStatus"] == "PARTIAL"
    assert summary["trackedExecutionIds"] == ["exec-1", "exec-2"]
    assert summary["sourceAvailability"] == {
        "violationInstances": True,
        "resourceExecutions": True,
    }
    assert summary["recordCounts"] == {
        "violationInstances": 2,
        "resourceExecutions": 2,
        "total": 4,
    }
    assert [item["source"] for item in summary["records"]] == [
        "violation-instance",
        "violation-instance",
        "resource-execution",
        "resource-execution",
    ]
    assert [item["message"] for item in summary["failureMessages"]] == [
        "violation instance failed",
        "resource execution failed",
    ]


@pytest.mark.parametrize(
    ("violation_statuses", "resource_statuses", "expected"),
    [
        (["SUCCESS"], [], "SUCCESS"),
        (["FAILED"], [], "FAILED"),
        (["EXECUTING"], [], "EXECUTING"),
        (["SUCCESS", "FAILED"], [], "PARTIAL"),
        (["SUCCESS", "EXECUTING"], [], "PARTIAL"),
    ],
)
def test_build_tracking_summary_collapses_overall_status(
    violation_statuses,
    resource_statuses,
    expected,
):
    violation_instances = [
        tracker.normalize_violation_instance(
            {
                "id": f"vio-inst-{index}",
                "violationId": "vio-1",
                "taskInstanceId": f"exec-{index}",
                "status": status,
            }
        )
        for index, status in enumerate(violation_statuses, start=1)
    ]
    resource_executions = [
        tracker.normalize_resource_execution(
            {
                "id": f"res-exec-{index}",
                "policyViolationId": "vio-1",
                "executionId": f"exec-{index}",
                "status": status,
            }
        )
        for index, status in enumerate(resource_statuses, start=1)
    ]

    summary = tracker.build_tracking_summary(
        violation_id="vio-1",
        violation_instances=violation_instances,
        resource_executions=resource_executions,
        resource_executions_available=bool(resource_statuses),
    )

    assert summary["overallStatus"] == expected


def test_render_tracking_output_outputs_structured_block():
    summary = tracker.build_tracking_summary(
        violation_id="vio-1",
        violation_instances=[
            tracker.normalize_violation_instance(
                {
                    "id": "vio-inst-1",
                    "violationId": "vio-1",
                    "taskInstanceId": "exec-1",
                    "status": "SUCCESS",
                }
            )
        ],
        resource_executions=[],
        resource_executions_available=True,
    )

    output = tracker.render_tracking_output(summary)

    assert "Violation vio-1: SUCCESS" in output
    assert "##COST_EXECUTION_TRACK_START##" in output
    assert "##COST_EXECUTION_TRACK_END##" in output
    payload = output.split("##COST_EXECUTION_TRACK_START##\n", 1)[1].split(
        "\n##COST_EXECUTION_TRACK_END##",
        1,
    )[0]
    assert json.loads(payload) == summary


def test_main_queries_instances_and_resource_executions(monkeypatch, capsys):
    calls = []

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {}, {}

    def fake_get(url, headers, params, verify, timeout):
        calls.append({"url": url, "params": params, "headers": headers})
        if url.endswith("/compliance-policies/violation-instances/search"):
            return DummyResponse(
                body={
                    "content": [
                        {
                            "id": "vio-inst-1",
                            "violationId": "vio-1",
                            "taskInstanceId": "exec-1",
                            "resourceName": "vm-prod-01",
                            "status": "FAILED",
                            "violationMessage": "violation instance failed",
                        },
                        {
                            "id": "vio-inst-2",
                            "violationId": "vio-1",
                            "taskInstanceId": "exec-2",
                            "resourceName": "vm-prod-02",
                            "status": "SUCCESS",
                        },
                    ]
                }
            )
        if url.endswith("/compliance-policies/resource-executions/search"):
            execution_id = params["executionId"]
            if execution_id == "exec-1":
                return DummyResponse(
                    body={
                        "content": [
                            {
                                "id": "res-exec-1",
                                "policyViolationId": "vio-1",
                                "executionId": "exec-1",
                                "resourceName": "vm-prod-01",
                                "status": "FAILED",
                                "errMsg": "resource execution failed",
                            }
                        ]
                    }
                )
            return DummyResponse(
                body={
                    "content": [
                        {
                            "id": "res-exec-2",
                            "policyViolationId": "vio-1",
                            "executionId": "exec-2",
                            "resourceName": "vm-prod-02",
                            "status": "SUCCESS",
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(tracker, "require_config", fake_require_config)
    monkeypatch.setattr(tracker.requests, "get", fake_get)
    monkeypatch.setattr(sys, "argv", ["track_execution.py", "--id", "vio-1"])

    assert tracker.main() == 0
    output = capsys.readouterr().out

    assert calls[0]["url"].endswith("/compliance-policies/violation-instances/search")
    assert calls[1]["url"].endswith("/compliance-policies/resource-executions/search")
    assert calls[2]["url"].endswith("/compliance-policies/resource-executions/search")
    assert "##COST_EXECUTION_TRACK_START##" in output
    payload = output.split("##COST_EXECUTION_TRACK_START##\n", 1)[1].split(
        "\n##COST_EXECUTION_TRACK_END##",
        1,
    )[0]
    summary = json.loads(payload)
    assert summary["overallStatus"] == "PARTIAL"
    assert summary["sourceAvailability"]["resourceExecutions"] is True
    assert [item["message"] for item in summary["failureMessages"]] == [
        "violation instance failed",
        "resource execution failed",
    ]


def test_main_handles_unavailable_resource_execution_data(monkeypatch, capsys):
    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {}, {}

    def fake_get(url, headers, params, verify, timeout):
        if url.endswith("/compliance-policies/violation-instances/search"):
            return DummyResponse(
                body={
                    "content": [
                        {
                            "id": "vio-inst-1",
                            "violationId": "vio-1",
                            "taskInstanceId": "exec-1",
                            "resourceName": "vm-prod-01",
                            "status": "EXECUTING",
                        }
                    ]
                }
            )
        raise requests.RequestException("resource execution endpoint unavailable")

    monkeypatch.setattr(tracker, "require_config", fake_require_config)
    monkeypatch.setattr(tracker.requests, "get", fake_get)
    monkeypatch.setattr(sys, "argv", ["track_execution.py", "--id", "vio-1"])

    assert tracker.main() == 0
    output = capsys.readouterr().out

    assert "resource executions were not queried" not in output
    payload = output.split("##COST_EXECUTION_TRACK_START##\n", 1)[1].split(
        "\n##COST_EXECUTION_TRACK_END##",
        1,
    )[0]
    summary = json.loads(payload)
    assert summary["overallStatus"] == "EXECUTING"
    assert summary["sourceAvailability"]["resourceExecutions"] is False
    assert summary["resourceExecutions"] == []
    assert summary["warnings"]
    assert "resource-executions/search request failed" in summary["warnings"][0]
