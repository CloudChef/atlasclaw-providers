# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "alarm"
    / "scripts"
    / "list_alerts.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_list_alerts_module", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def extract_meta(output: str):
    match = re.search(
        r"##ALARM_META_START##\s*(.*?)\s*##ALARM_META_END##",
        output,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def extract_resource_coverage(output: str):
    match = re.search(
        r"##RESOURCE_ALERT_COVERAGE_START##\s*(.*?)\s*##RESOURCE_ALERT_COVERAGE_END##",
        output,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def localized(default: str, zh_cn: str) -> dict[str, object]:
    return {
        "default": default,
        "translations": {
            "en-US": default,
            "zh-CN": zh_cn,
        },
    }


def test_main_prints_numbered_summary_and_meta_block(monkeypatch):
    module = load_module()
    captured = {}
    payload = {
        "content": [
            {
                "id": "alert-1",
                "alarmPolicyId": "policy-1",
                "alarmPolicyName": "CPU High",
                "status": "ALERT_FIRING",
                "level": 3,
                "triggerAt": "2026-03-28T01:02:03Z",
                "lastTriggerAt": "2026-03-28T04:05:06Z",
                "triggerCount": 4,
                "deploymentId": "deployment-1",
                "deploymentName": "prod-app",
                "entityInstanceId": ["entity-1"],
                "entityInstanceName": "vm-01",
                "nodeInstanceId": "node-1",
                "targetEntityId": "target-1",
                "resourceExternalId": "i-abc",
                "resourceExternalName": "worker-01",
            },
            {
                "id": "alert-2",
                "alarmPolicyId": "policy-2",
                "alarmPolicyName": "Memory High",
                "status": "ALERT_MUTED",
                "level": 2,
                "triggerAt": "2026-03-28T02:00:00Z",
                "lastTriggerAt": "2026-03-28T03:00:00Z",
                "triggerCount": 1,
                "deploymentId": "deployment-2",
                "deploymentName": "qa-app",
                "entityInstanceId": ["entity-2"],
                "entityInstanceName": "vm-02",
                "nodeInstanceId": "node-2",
                "resourceExternalId": "i-def",
                "resourceExternalName": "worker-02",
            },
        ],
        "totalElements": 2,
    }

    def fake_get_json(path, *, params=None, timeout=60):
        captured["path"] = path
        captured["params"] = params
        return payload

    monkeypatch.setattr(module, "get_json", fake_get_json)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(
            [
                "--status",
                "ALERT_FIRING",
                "--days",
                "3",
                "--size",
                "10",
                "--target-entity-id",
                "target-1",
            ]
        )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "Found 2 alert(s):" in output
    assert "| # | Policy | Status | Level | Resource |" in output
    assert "| 1 | CPU High | ALERT_FIRING | 3 | worker-01 |" in output
    assert "worker-01" in output
    assert captured["path"] == "/alarm-alert?query"
    assert captured["params"]["status"] == ["ALERT_FIRING"]
    assert captured["params"]["size"] == 10
    assert captured["params"]["targetEntityId"] == "target-1"

    meta = extract_meta(output)
    assert len(meta) == 2
    assert meta[0]["index"] == 1
    assert meta[0]["object_type"] == "alarm_alert"
    assert meta[0]["object_id"] == "alert-1"
    assert meta[0]["object_name"] == "CPU High"
    assert meta[0]["object_actions"] == [
        {
            "action_id": "view_detail",
            "kind": "agent_prompt",
            "display_label": localized("View details", "查看详情"),
            "agent_prompt": localized("Analyze alert alert-1", "分析告警 alert-1"),
            "effect": "read",
            "tone": "default",
        }
    ]
    assert meta[0]["alertId"] == "alert-1"
    assert meta[0]["alarmPolicyId"] == "policy-1"
    assert meta[0]["status"] == "ALERT_FIRING"
    assert meta[0]["level"] == 3
    assert meta[0]["deploymentId"] == "deployment-1"
    assert meta[0]["nodeInstanceId"] == "node-1"
    assert meta[0]["targetEntityId"] == "target-1"
    assert meta[0]["resourceExternalId"] == "i-abc"
    assert meta[0]["resourceExternalName"] == "worker-01"
    assert meta[1]["index"] == 2
    assert meta[1]["alertId"] == "alert-2"
    assert meta[1]["alarmPolicyId"] == "policy-2"
    assert meta[1]["status"] == "ALERT_MUTED"
    assert meta[1]["level"] == 2


def test_main_prints_empty_state(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "get_json", lambda *args, **kwargs: {"content": [], "totalElements": 0})

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["--status", "ALERT_RESOLVED"])

    output = stdout.getvalue()
    assert exit_code == 0
    assert "No alerts found." in output
    assert extract_meta(output) == []


def test_main_prints_error_and_returns_non_zero(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "get_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["--status", "ALERT_FIRING"])

    output = stdout.getvalue()
    assert exit_code == 1
    assert "[ERROR] boom" in output


def test_resource_mode_collects_current_and_recent_exact_matches(monkeypatch):
    module = load_module()
    calls = []

    monkeypatch.setattr(
        module,
        "resolve_alert_resource_target",
        lambda args: ("resource-1", "vm-01"),
    )

    def fake_get_json(path, *, params=None, timeout=60):
        calls.append({"path": path, **dict(params or {})})
        is_resolved = params.get("status") == ["ALERT_RESOLVED"]
        alert = {
            "id": "alert-resolved" if is_resolved else "alert-current",
            "alarmPolicyName": "Recovered CPU" if is_resolved else "CPU High",
            "status": "ALERT_RESOLVED" if is_resolved else "ALERT_FIRING",
            "targetEntityId": "resource-1",
            "entityInstanceName": "vm-01",
            "resourceExternalName": "vm-01",
        }
        return {"content": [alert], "totalElements": 1}

    monkeypatch.setattr(module, "get_json", fake_get_json)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(
            ["--resource-name", "vm-01", "--resource-alert-scope", "current_and_recent"]
        )

    output = stdout.getvalue()
    meta = extract_meta(output)
    coverage = extract_resource_coverage(output)

    assert exit_code == 0
    assert len(calls) == 2
    current_calls = [call for call in calls if call["status"] != ["ALERT_RESOLVED"]]
    resolved_calls = [call for call in calls if call["status"] == ["ALERT_RESOLVED"]]
    assert all(call["path"] == "/alarm-alert?query" for call in calls)
    assert all(call["targetEntityId"] == "resource-1" for call in calls)
    assert all("triggerAtMin" not in call and "triggerAtMax" not in call for call in current_calls)
    assert all("triggerAtMin" in call and "triggerAtMax" in call for call in resolved_calls)
    assert all("resolveAtMin" not in call and "resolveAtMax" not in call for call in resolved_calls)
    assert [item["alertId"] for item in meta] == ["alert-current", "alert-resolved"]
    assert meta[0]["alertLifecycle"] == "current"
    assert meta[0]["resourceMatchBasis"] == "resource_id"
    assert meta[0]["targetEntityId"] == "resource-1"
    assert meta[1]["alertLifecycle"] == "resolved_trigger_lookback"
    assert coverage["associationStatus"] == "complete"
    assert coverage["matchedCount"] == 2
    assert coverage["resolvedTriggerLookbackDays"] == 7


def test_resource_mode_preserves_cross_lifecycle_race_as_partial(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "resolve_alert_resource_target",
        lambda args: ("resource-1", "vm-01"),
    )

    def fake_get_json(path, *, params=None, timeout=60):
        is_resolved = params.get("status") == ["ALERT_RESOLVED"]
        return {
            "content": [
                {
                    "id": "alert-raced",
                    "status": "ALERT_RESOLVED" if is_resolved else "ALERT_FIRING",
                    "targetEntityId": "resource-1",
                    "entityInstanceName": "vm-01",
                }
            ]
        }

    monkeypatch.setattr(module, "get_json", fake_get_json)
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["--resource-name", "vm-01"])

    meta = extract_meta(stdout.getvalue())
    coverage = extract_resource_coverage(stdout.getvalue())

    assert exit_code == 0
    assert [item["status"] for item in meta] == ["ALERT_FIRING", "ALERT_RESOLVED"]
    assert [item["alertLifecycle"] for item in meta] == [
        "current",
        "resolved_trigger_lookback",
    ]
    assert coverage["associationStatus"] == "partial"
    assert coverage["matchedCount"] == 2
    assert coverage["lifecycleConflictCount"] == 1
    assert coverage["errors"] == ["cross_lifecycle.alertId:conflicting_observations"]


def test_resource_mode_rejects_name_match_with_wrong_target_entity_id(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "resolve_alert_resource_target",
        lambda args: ("resource-1", "vm-01"),
    )
    monkeypatch.setattr(
        module,
        "get_json",
        lambda *args, **kwargs: {
            "content": [
                {
                    "id": "alert-other",
                    "status": "ALERT_FIRING",
                    "targetEntityId": "resource-10",
                    "entityInstanceName": "vm-010",
                    "resourceExternalName": "vm-01",
                }
            ]
        },
    )

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["--resource-name", "vm-01"])

    output = stdout.getvalue()
    coverage = extract_resource_coverage(output)
    assert exit_code == 0
    assert extract_meta(output) == []
    assert coverage["associationStatus"] == "partial"
    assert coverage["matchedCount"] == 0
    assert coverage["unverifiedCandidateCount"] == 2
    assert "absence of matched alerts is not proof" in output


def test_resource_mode_keeps_matches_when_one_query_fails(monkeypatch):
    module = load_module()
    call_count = 0
    monkeypatch.setattr(
        module,
        "resolve_alert_resource_target",
        lambda args: ("resource-1", "vm-01"),
    )

    def fake_get_json(path, *, params=None, timeout=60):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("temporary failure")
        return {
            "content": [
                {
                    "id": "alert-resolved",
                    "status": "ALERT_RESOLVED",
                    "targetEntityId": "resource-1",
                    "entityInstanceName": "vm-01",
                }
            ]
        }

    monkeypatch.setattr(module, "get_json", fake_get_json)
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["--resource-name", "vm-01"])

    output = stdout.getvalue()
    coverage = extract_resource_coverage(output)
    assert exit_code == 0
    assert extract_meta(output)[0]["alertId"] == "alert-resolved"
    assert extract_meta(output)[0]["alertLifecycle"] == "resolved_trigger_lookback"
    assert coverage["associationStatus"] == "partial"
    assert coverage["queriesSucceeded"] == 1
    assert coverage["errors"] == ["current.targetEntityId:query_failed"]


def test_resource_mode_rejects_malformed_success_response(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "resolve_alert_resource_target",
        lambda args: ("resource-1", "vm-01"),
    )
    monkeypatch.setattr(module, "get_json", lambda *args, **kwargs: {})

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(
            ["--resource-name", "vm-01", "--resource-alert-scope", "current"]
        )

    coverage = extract_resource_coverage(stdout.getvalue())
    assert exit_code == 0
    assert coverage["associationStatus"] == "indeterminate"
    assert coverage["queriesSucceeded"] == 0
    assert coverage["errors"] == ["current.targetEntityId:invalid_response"]


def test_resource_mode_current_empty_message_does_not_claim_recent_history(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "resolve_alert_resource_target",
        lambda args: ("resource-1", "vm-01"),
    )
    monkeypatch.setattr(
        module,
        "get_json",
        lambda *args, **kwargs: {"content": [], "totalElements": 0},
    )

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(
            ["--resource-name", "vm-01", "--resource-alert-scope", "current"]
        )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "No exactly matched current firing or muted alerts" in output
    assert "No exactly matched current or recent alerts" not in output


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--days", "0"),
        ("--days", "-1"),
        ("--page", "0"),
        ("--size", "0"),
    ],
)
def test_parse_args_rejects_non_positive_integers(flag, value):
    module = load_module()

    with pytest.raises(SystemExit):
        module.parse_args([flag, value])
